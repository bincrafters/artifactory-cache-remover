# Bincrafters Cache Remover

This project has internal propose for Bincrafters, and its goal is removing cached packages from Artifactory.

### Usage

This script provides two possibilities: 

#### List all empty cached packages

If you want to list all storages which are "empty" (only contains index.json files):

    python bincrafters-cache-remover.py list --remote=bincrafters --repository=bintray-conan-cache --json=bintray-conan-cache.json

This command will take minutes, as each repository level requires a get HTTP request. All information collected will be 
stored in the json file passed by argument. The API Token is not required on this step.


#### Remove all empty packages from cache

If you want to delete all storages which are listed in a json file:

    python bincrafters-cache-remover.py remove --json=bintray-conan-cache.json --token=<Artifactory Access Token>

To avoid mistyping, both arguments `--remote` and `--repository` are ignored. Instead, all information will be collected
from the json file. This command asks the user before executing, and only 'YES' is accepted to prevent any mistake.


#### Verbosity

If you want to see more messages, pass `--log-level=debug` as argument.

#### Dry Run

If you are afraid of deleting, pass `--dry-run` with `remove` command. It will print messages only.


#### LICENSE
[MIT](LICENSE)


