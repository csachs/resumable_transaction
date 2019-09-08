import os
import sys
import tempfile
import datetime
import warnings
import traceback

from collections import namedtuple

import jsonpickle


class Configuration:
    TRANSACTION_STORAGE_DIRECTORY = '/tmp/'
    TRANSACTION_PREFIX = 'transaction'

    CLEANUP = True

    CHATTY_EXCEPTIONS = True


class States:
    PENDING = 'pending'

    STARTED = 'started'
    FINISHED = 'finished'

    ABORTED = 'aborted'
    ERROR = 'error'


TransactionStep = namedtuple('TransactionStep',
                             'state, fun, args, kwargs, return_target, kwargs_from_state, started_at, finished_at'
                             )


class Transaction:
    def __init__(self):
        self.backing = None

        self.transaction_state = States.PENDING

        self.error_info = (None, None, None)

        self.state = {}
        self.steps = []

        self.started_at = None
        self.finished_at = None

    def do(self, fun, *args, **kwargs):

        if '_return' in kwargs:
            return_target = kwargs['_return']
            del kwargs['_return']
        else:
            return_target = None

        kwargs_from_state = {}

        for k, v in list(kwargs.items()):
            if k[0] == '_':
                # if v in self.state:  # remove # why was this still inside?
                kwargs_from_state[k[1:]] = v
                del kwargs[k]

        step = TransactionStep(
                state=States.PENDING,
                fun=fun,
                args=args,
                kwargs=kwargs,
                return_target=return_target,
                kwargs_from_state=kwargs_from_state,
                started_at=None,
                finished_at=None
            )

        self.steps.append(step)

    @staticmethod
    def step_to_human_readable(step):
        if step.fun is None:
            warnings.warn("Tried to print a step with <None> as function. This likely means, deserialization failed. " +
                          "If the transaction step functions are not part of a correctly installed module, " +
                          "the defining file needs to be loaded beforehand.",
                          RuntimeWarning
                          )

        return (('state[\'%s\'] = ' % step.return_target if step.return_target else '') + (
                step.fun.__name__ if step.fun else '{DESERIALIZATION_FAILED}') +
                '(' + ', '.join(
                    ['%r' % a for a in step.args] +
                    ['%s=%r' % (k, v) for k, v in step.kwargs.items()] +
                    ['%s=state[%r]' % (k, v) for k, v in step.kwargs_from_state.items()]
                ) + ')')

    def human_readable(self):
        result = [
            "Transaction state: " + repr(self.transaction_state),
            "Error Information: " + repr(self.error_info),
            "Started at:        " + self.started_at.isoformat(),
            "Finished/Ended at: " + self.finished_at.isoformat(),
            "Elapsed time:      " + "%.3fs" % ((self.finished_at - self.started_at).total_seconds()),
            "",
            "Steps:",
            ""
        ]

        for step in self.steps:
            result.append(
                self.step_to_human_readable(step) +
                "  # " + step.state + (
                    ' at %.3fs' % ((step.started_at - self.started_at).total_seconds())
                    if step.started_at
                    else ''
                ) + (
                    ' took %.3fs' % ((step.finished_at - step.started_at).total_seconds())
                    if step.started_at and step.finished_at
                    else ''
                )
            )

        return "\r\n".join(result)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.transaction_state = States.ERROR

            self.error_info = (
                exc_type,
                exc_val,
                traceback.extract_tb(exc_tb)
            )

        self.write_to_disk()

        if exc_type:
            return

        self.execute()

    def execute(self, only_pending=True, treat_error_as_pending=True):

        self.transaction_state = States.STARTED
        self.started_at = datetime.datetime.now()
        self.write_to_disk()

        for n in range(len(self.steps)):
            step = self.steps[n]
            assert step.fun

            if not treat_error_as_pending and step.state == States.ERROR:
                continue

            if (only_pending and step.state != States.PENDING and
                    not (treat_error_as_pending and step.state == States.ERROR)):
                continue

            try:
                # noinspection PyProtectedMember
                step = step._replace(state=States.STARTED,
                                     started_at=datetime.datetime.now())

                self.steps[n] = step
                self.write_to_disk()

                args = step.args

                kwargs = step.kwargs.copy()
                kwargs.update(
                    {key: self.state[value] for key, value in step.kwargs_from_state.items()}
                )

                result = step.fun(
                    *args,
                    **kwargs
                )

                if step.return_target:
                    self.state[step.return_target] = result

                # noinspection PyProtectedMember
                step = step._replace(state=States.FINISHED, finished_at=datetime.datetime.now())

                self.steps[n] = step
                self.write_to_disk()

            except Exception as e:
                self.error_info = (type(e), e, traceback.extract_tb(sys.exc_info()[2]))

                # noinspection PyProtectedMember
                step = step._replace(state=States.ERROR, finished_at=datetime.datetime.now())
                self.steps[n] = step

                self.finished_at = datetime.datetime.now()
                self.transaction_state = States.ABORTED

                self.write_to_disk()
                raise RuntimeError(
                    "Transaction failed. It was stored to disk and can be inspected/resumed later."
                    + (" It is stored under \"%s\"." % (self.backing,) if Configuration.CHATTY_EXCEPTIONS else '')
                )

        self.transaction_state = States.FINISHED
        self.finished_at = datetime.datetime.now()
        self.write_to_disk()

        if Configuration.CLEANUP:
            os.unlink(self.backing)

    def write_to_disk(self):
        handle, new_filename = tempfile.mkstemp(
            suffix='.json',
            dir=Configuration.TRANSACTION_STORAGE_DIRECTORY,
            prefix=Configuration.TRANSACTION_PREFIX + datetime.datetime.now().strftime('-%Y%m%d-%H%M%S-')
        )

        serialized = jsonpickle.dumps(self).encode('utf-8')

        bytes_written = os.write(handle, serialized)

        if bytes_written != len(serialized):
            raise IOError('Writing to the transaction file failed. This is non-recoverable.')

        if self.backing:
            os.rename(new_filename, self.backing)
        else:
            self.backing = new_filename

        os.close(handle)


def main():
    import sys
    if len(sys.argv) < 3:
        print("Usage: <script> <inspect,replay> <transaction.json> [python file]")
        return

    action, file_name = sys.argv[1], sys.argv[2]

    if len(sys.argv) == 4:
        python_file = sys.argv[3]

        import importlib.util
        module_spec = importlib.util.spec_from_file_location('__not_main__', python_file)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        sys.modules['__main__'] = module

    def load_transaction(_file_name):
        with open(_file_name, 'r') as fp:
            return jsonpickle.loads(fp.read())

    if action == 'resume':
        t = load_transaction(file_name)
        t.execute()
    elif action == 'inspect':
        t = load_transaction(file_name)
        print(t.human_readable())
    else:
        raise NotImplementedError
