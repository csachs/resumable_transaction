# resumable_transaction

A little Python package (beta-level) aimed at allowing to pause a transaction upon failure and resume it later on.

*Please note, that there is currently no support for reverting anything!*

The library can be helpful when e.g. external resources are modified using Python, and even in case of an error, the system should be brought to a consistent state later. (And certain steps are un-undoable, hence no reverting but letting e.g. an administrator finish the steps.)

## Example

Let our example be named `test.py`, it will run two similar transactions, which would create a file in `/tmp` if it does not exist, or fail otherwise.

```python
# test.py
from resumable_transaction import Transaction

import os


def create_and_write_file_in_tmp(file_name, data):
    # create a file if it does not exist, fail if
    with os.fdopen(os.open(file_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY), 'w') as fp:
        fp.write(data)


def read_file_contents(file_name):
    with open(file_name) as fp:
        return fp.read()


def print_incoming_data(our_argument_name):
    print(our_argument_name)


if __name__ == '__main__':
    for n in [1, 2]:
        with Transaction() as t:
            file_name = "/tmp/our_test_file"
            t.do(create_and_write_file_in_tmp, file_name, "Hello World, the {n}. time".format(n=n))
            t.do(read_file_contents, file_name, _return='some_name_to_store')
            t.do(print_incoming_data, _our_argument_name='some_name_to_store')
```

Running the example, it will fail as expected, as after the first `for`-iteration, the file will already be present:

```bash
% python test.py
Hello World, the 1. time
Traceback (most recent call last):
  ...
  File "test.py", line 8, in create_and_write_file_in_tmp
    with os.fdopen(os.open(file_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY), 'w') as fp:
FileExistsError: [Errno 17] File exists: '/tmp/our_test_file'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  ...
RuntimeError: Transaction failed. It was stored to disk and can be inspected/resumed later. It is stored under "/tmp/transaction.json".
```

While the second transaction has failed, we can inspect its contents and see what happened by calling the module with the action `inspect`. Note that `test.py` is added as last parameter, since the module needs to have access to the functions defined in `test.py`. If a we would have used functions from correctly installed modules, we would not have to add the file name manually.

```bash
% python -m resumable_transaction inspect /tmp/transaction.json test.py
Transaction state: 'aborted'
Error Information: (<class 'FileExistsError'>, FileExistsError(17, 'File exists'), [<FrameSummary file resumable_transaction/__init__.py, line 170 in execute>, <FrameSummary file test.py, line 8 in create_and_write_file_in_tmp>])
Started at:        2019-09-08T17:13:35.136085
Finished/Ended at: 2019-09-08T17:13:35.137030
Elapsed time:      0.001s

Steps:

create_and_write_file_in_tmp('/tmp/our_test_file', 'Hello World, the 2. time')  # error at 0.000s took 0.001s
state['some_name_to_store'] = read_file_contents('/tmp/our_test_file')  # pending
print_incoming_data(our_argument_name=state['some_name_to_store'])  # pending
```

Inspect showed us the problem, let's fix it by removing the file and continuing the transaction using `resume`:

```bash
% rm /tmp/our_test_file
% python -m resumable_transaction resume /tmp/transaction.json test.py 
Hello World, the 2. time
```
