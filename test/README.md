# ICT-Capstone-Project-2-13

## Setup for Unit Testing toolchain

This project uses the [pytest](https://docs.pytest.org/en/stable/index.html) unit testing framework. A brief setup of pytest is documented below, for more information please refer to the pytest [how-to guides](https://docs.pytest.org/en/stable/how-to/index.html) and [reference guides](https://docs.pytest.org/en/stable/reference/index.html).

## Installing pytest
Pytest is installed as a user-accessible application through `pip`.

```bash
>>> pip install -U pytest
```

Please note that depending on your OS you may have to install pytest in a different manner, for example via `pacman` on Arch Linux.

Verify that pytest has been installed correctly:
```bash
>>> pytest --version
pytest 9.1.1
```

*Note that unit tests have been performed using pytest version 9.1.1*

## Invoking pytest and running tests

From the root of this project (not this testing directory), invoke the `pytest` command. All available tests will be run.

Tests in specific modules or directories can be run by supplying the desired file or directory as an argument to pytest.
