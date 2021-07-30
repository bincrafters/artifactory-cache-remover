""" Bincrafters Cache Remover

This script removes all dummy packages from cached repositories in Artifactory.
Some important notes:
- Those *-cache Repositories in Artifactory, actually are Storage
- If you try to list all repositories using API, *-cache are not there
- Storages only return the first folder/file level when listing with the API
- We need to execute a recursive search to check if a Storage is empty or not
- If a Storage contains only index.json files, Then is considered as Empty
- All Empty Storages should be removed

Artifactory API reference for this script:

- https://www.jfrog.com/confluence/display/JFROG/Artifactory+REST+API#ArtifactoryRESTAPI-Authentication
- https://www.jfrog.com/confluence/display/JFROG/Artifactory+REST+API#ArtifactoryRESTAPI-DeleteItem
- https://www.jfrog.com/confluence/display/JFROG/Artifactory+REST+API#ArtifactoryRESTAPI-FolderInfo

"""
import textwrap
import json
import logging
import requests
import argparse
import os
import sys


logger = logging.getLogger(__name__)


def parse_arguments():
    """ User command arguments.
        List and Remove are separated commands, to avoid any possible mistake when typing
    :return: Dictionary with argv
    """
    parser = argparse.ArgumentParser(usage="Remove cache from Artifactory")
    parser.add_argument("command", choices=["list", "remove"], help="Execute an action. Remove or List packages.")
    parser.add_argument("-j", "--json", help="Save listed packages into a json file")
    parser.add_argument("-f", "--force", help="Override json if already exist", action="store_true")
    parser.add_argument("-e", "--remote", help="Artifactory remote name e.g. bincrafters")
    parser.add_argument("-r", "--repository", help="Repository to be searched e.g. bintray-conan-cache")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Do not execute real commands.")
    parser.add_argument("-t", "--token", help="Artifactory token to execute actions")
    parser.add_argument("-ll", "--log-level", choices=["debug", "info", "warning", "error"], default="info",
                        help="Set the logging level. Default is INFO.")
    return parser.parse_args()


def validate_arguments(args):
    """ Check arguments rules.
        Only remove repositories by a JSON file, so we "reproduce" the same command.
    :param args: Application argvs
    """
    try:
        if args.command == "list" and args.json:
            if os.path.exists(os.path.abspath(args.json)) and not args.force:
                raise ValueError("The path indicated by `--json` already exists. Use `--force` to override.")
        elif args.command == "remove" and not args.json:
            raise ValueError("A json file is required to remove packages. Pass --json=<path>.")
        elif args.command == "remove" and not args.token:
            raise ValueError("Remove action requires Artifactory token. Pass --token with your admin token.")
        elif args.command == "remove" and (args.remote or args.repository):
            logger.warning("Remove command consumes Remote and Repository directly from JSON file only.")
    except ValueError as error:
        logger.error(f"ERROR: {error}")
        sys.exit(1)


def get_headers(token):
    """ Default to be used for GET/POST
    :param token: Artifactory API token
    :return: HTTP headers
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_api_url(remote):
    """ Default Artifactory API URL, based on remote name
    :param remote: Remote name (e.g. bincrafters)
    :return: Artifactory URL
    """
    return f"https://{remote}.jfrog.io/artifactory/api"


def get_storage_url(remote, repository):
    """ Get a Artifactory Storage URL
    :param remote: Artifactory remote name (e.g. bincrafters)
    :param repository: Repository name (e.g. bintray-conan-cache)
    :return: Storage URL
    """
    return get_api_url(remote) + f"/storage/{repository}"


def is_empty_package(remote, repository, storage, token):
    """ Execute a recursive call to validate is a storage is empty or not
    :param remote: Artifactory remote name e.g. bincrafters
    :param repository: Repository name e.g. bintray-conan-cache
    :param storage: Internal storage name e.g. user
    :param token: Artifactory Access Token. Not really required for public repositories.
    :return: True if storage is empty. Otherwise, False.
    """
    logger.info(f"Recursive call to URI: {storage}")
    repository_url = get_storage_url(remote, repository)
    uri = storage["uri"]
    logger.debug(f"Recursive call to URI: {uri}")
    result = recursive_search(repository_url, uri, token)
    logger.debug(f"Storage {uri} is empty: {result}")
    return result


def recursive_search(storage_path, uri, token):
    """ Search folder by folder until finding their files.
        If only index.json is found, then is considered empty
    :param storage_path: Artifactory Storage URL
    :param uri: Recursive folder path listed in the Storage
    :param token: Artifactory API Token
    :return: True is the Storage is Empty. Otherwise, False
    """
    url = storage_path + uri
    logger.debug(f"GET: {url}")
    response = requests.get(url, headers=get_headers(token)).json()
    logger.debug(f'CHILDREN: {response["children"]}')
    for child in response["children"]:
        if child["folder"] is False and child["uri"] != "/index.json":
            return False
        elif child["folder"] is True:
            return recursive_search(storage_path, uri + child["uri"], token)
    return True


def list_packages(remote, repository, json_path=None, token=None):
    """ List all empty repositories in Artifactory remote
        This method list the storages in the repository and one by one, look into for files which are not named
        as index.json. All storages identified as empty, will be stored in the json file.
    :param remote: Artifactory remote name e.g. bincrafters
    :param repository: Artifactory repository name e.g. bintray-conan-cache
    :param json_path: JSON file path to be saved with listed content
    :param token: Artifactory Access token for API. Not really required for public repositories.
    :return: Dictionary with all empty storages
    """
    url = get_storage_url(remote, repository)
    logger.debug(f"Storage URL: {url}")
    response = requests.get(url, headers=get_headers(token))
    json_response = response.json()
    children = json_response["children"]
    to_be_removed = []
    logger.debug("Storage count: {}".format(len(children)))
    for child in children:
        if is_empty_package(remote, repository, child, token):
            to_be_removed.append(child)
    logger.debug("Found {} empty packages.".format(len(to_be_removed)))
    json_response["children"] = to_be_removed
    if json_path:
        with open(json_path, 'w') as json_fd:
            json.dump(json_response, json_fd, indent=2, sort_keys=True)
    logger.debug(json_response)
    return json_response


def remove_packages(json_file, dryrun, token):
    """ Remove an entire Storage from Artifactory
       This command can not be undone, so that, the user MUST type 'YES'.
       To avoid any mistyping error, only JSON file is accepted to list what should be removed
    :param json_file: JSON file path generated by list command
    :param dryrun: Mock execution when enabled. Delete nothing
    :param token: Artifactory API token
    :return: None
    """

    json_content = json.load(open(json_file))
    children = json_content["children"]
    repository = json_content["repo"]
    check = str(input(textwrap.dedent(f"""
    !!!WARNING!!! Are you sure? This operation CAN NOT BE UNDONE!
    This action will DELETE {len(children)} packages from {repository}.
    Type 'YES' if you are sure: """))).strip()
    if check == "YES":
        if dryrun:
            logger.warning("Running Dry-run mode. No real deletion will be executed.")
        for child in children:
            url = json_content["uri"] + child["uri"]
            # Delete method can not be used with API. Instead, use directly url
            url = url.replace("/api/storage", "")
            logger.debug(f"Delete: {url}")
            if not dryrun:
                response = requests.delete(url=url, headers=get_headers(token))
                if not response.ok:
                    logger.error(f"Could not delete Storage: {response.text}")
            logger.info(f"Deleted with success: {url}")
    else:
        logger.error("Invalid answer, only 'YES' will be accepted. Good bye.")


def configure_logger(args):
    """ Configure the general logger instance
        Use stream only
        Info as default level
    :param args: Application arguments
    :return: None
    """
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    if args.log_level == "debug":
        logger.setLevel(logging.DEBUG)
    elif args.log_level == "warning":
        logger.setLevel(logging.WARNING)
    elif args.log_level == "error":
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.INFO)


def main():
    """ Main execution
        - Logging configuration
        - Read application arguments
        - Validate arguments
        - Run or Remove command or List command
    :return: None
    """
    args = parse_arguments()
    configure_logger(args)
    validate_arguments(args)
    if args.command == "list":
        logger.info(textwrap.dedent(f"""Executing list command ...
        Remote: {args.remote}
        Storage: {args.repository}
        """))
        list_packages(args.remote, args.repository, args.json)
    elif args.command == "remove":
        remove_packages(args.json, args.dry_run, args.token)


if __name__ == "__main__":
    main()
