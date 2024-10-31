#!/usr/bin/env python3
"""
This script fetches all releases from a GitHub repository starting from a given date,
differentiates between full releases and pre-releases (alpha, beta, etc.) according to
semantic versioning, filters by an optional package name, and saves the release tag and date pairs to a file.
"""

import argparse
import logging
import requests
import sys
import datetime
from urllib.parse import urlparse
from packaging.version import Version, InvalidVersion


def setup_logging():
    """Sets up the logging configuration."""
    logging.basicConfig(
        level=logging.DEBUG,  # Set to DEBUG for detailed output
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def parse_arguments():
    """
    Parses command-line arguments.

    Returns:
        tuple: GitHub repository URL, start date, output file name, package name, API token, include_prereleases.
    """
    parser = argparse.ArgumentParser(description='Fetch GitHub repository releases.')
    parser.add_argument('repo_url', help='GitHub repository URL')
    parser.add_argument('start_date', help='Start date in YYYY-MM-DD format')
    parser.add_argument(
        '-o', '--output', help='Output file name'
    )
    parser.add_argument(
        '-p', '--package-name', help='Package name to filter releases', default=None
    )
    parser.add_argument(
        '-t', '--token', help='GitHub Personal Access Token', default=None
    )
    parser.add_argument(
        '--include-prereleases', action='store_true',
        help='Include pre-releases in the output'
    )
    args = parser.parse_args()
    return (
        args.repo_url, args.start_date, args.output,
        args.package_name, args.token, args.include_prereleases
    )


def parse_github_url(repo_url):
    """
    Parses the GitHub repository URL to extract the owner and repository name.

    Args:
        repo_url (str): The GitHub repository URL.

    Returns:
        tuple: Owner and repository name.
    """
    try:
        parsed_url = urlparse(repo_url)
        path_parts = parsed_url.path.strip('/').split('/')
        if len(path_parts) >= 2:
            owner = path_parts[0]
            repo = path_parts[1]
            return owner, repo
        else:
            logging.error('Invalid GitHub repository URL.')
            sys.exit(1)
    except Exception as e:
        logging.error(f'Error parsing GitHub URL: {e}')
        sys.exit(1)


def fetch_releases(owner, repo, token=None):
    """
    Fetches all releases from the GitHub API.

    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        token (str): GitHub Personal Access Token.

    Returns:
        list: List of releases.
    """
    releases = []
    page = 1
    per_page = 100
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'token {token}'

    while True:
        try:
            url = f'https://api.github.com/repos/{owner}/{repo}/releases?page={page}&per_page={per_page}'
            logging.info(f'Fetching releases from {url}')
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            page_releases = response.json()
            if not page_releases:
                break
            releases.extend(page_releases)
            page += 1
        except requests.exceptions.RequestException as e:
            logging.error(f'Error fetching releases: {e}')
            sys.exit(1)
    return releases


def extract_version(tag_name, package_name=None):
    """
    Extracts the version number from a tag name.

    Args:
        tag_name (str): The tag name.
        package_name (str): The package name to filter.

    Returns:
        Version or None: Parsed Version object or None if invalid.
    """
    try:
        if package_name:
            expected_prefix = f"{package_name}=="
            if tag_name.startswith(expected_prefix):
                version_str = tag_name[len(expected_prefix):]
            else:
                logging.debug(f"Tag '{tag_name}' does not match package name '{package_name}'")
                return None
        else:
            # No package_name specified
            version_str = tag_name

        # Remove any leading 'v' from version string
        if version_str.startswith('v'):
            version_str = version_str[1:]

        version = Version(version_str)
        return version
    except InvalidVersion as e:
        logging.debug(f"Invalid version '{tag_name}': {e}")
        return None


def filter_releases(releases, start_date, package_name=None, include_prereleases=False):
    """
    Filters releases based on the start date, package name, and whether they are full releases.

    Args:
        releases (list): List of releases.
        start_date (datetime.date): The start date.
        package_name (str): Package name to filter releases.
        include_prereleases (bool): Whether to include pre-releases.

    Returns:
        list: Filtered list of (tag_name, release_date) tuples.
    """
    filtered_releases = []
    for release in releases:
        try:
            release_date_str = release['published_at']
            release_date = datetime.datetime.strptime(
                release_date_str, '%Y-%m-%dT%H:%M:%SZ'
            ).date()
            if release_date < start_date:
                logging.debug(f"Skipping release '{release['tag_name']}' before start date")
                continue

            tag_name = release['tag_name']
            version = extract_version(tag_name, package_name)
            if version is None:
                continue

            if not include_prereleases and version.is_prerelease:
                logging.debug(f"Skipping pre-release '{tag_name}'")
                continue

            filtered_releases.append((tag_name, release_date))
        except Exception as e:
            logging.error(f'Error processing release {release}: {e}')
    return filtered_releases


def save_to_file(releases, output_file):
    """
    Saves the releases to a file.

    Args:
        releases (list): List of (tag_name, release_date) tuples.
        output_file (str): The output file name.
    """
    try:
        with open(output_file, 'w') as f:
            for tag, date in releases:
                f.write(f'{tag}, {date}\n')
        logging.info(f'Releases saved to {output_file}')
    except Exception as e:
        logging.error(f'Error writing to file {output_file}: {e}')
        sys.exit(1)


def main():
    """Main function."""
    setup_logging()
    try:
        (
            repo_url, start_date_str, output_file,
            package_name, token, include_prereleases
        ) = parse_arguments()
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        owner, repo = parse_github_url(repo_url)
        releases = fetch_releases(owner, repo, token)
        filtered_releases = filter_releases(
            releases, start_date, package_name, include_prereleases
        )
        for tag, date in filtered_releases:
            print(f'{tag}, {date}')
        # Generate output file name if not provided
        if not output_file:
            if package_name:
                output_file = f"{owner}_{repo}_{package_name}_releases.txt"
            else:
                output_file = f"{owner}_{repo}_releases.txt"
            logging.info(f"No output file provided. Using default: {output_file}")
        save_to_file(filtered_releases, output_file)
    except Exception as e:
        logging.error(f'An unexpected error occurred: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
