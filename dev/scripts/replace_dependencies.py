from __future__ import annotations

import argparse
import fileinput
from re import sub

from pip._internal.utils.packaging import get_requirement


def update_setup_cfg(rc_provider_packages: list[str]):
    """
    Replaces the given provider packages in the setup.cfg with the given pinned RC versions.
    :param rc_provider_packages: list of RC provider packages to be replaced
    """
    for package in rc_provider_packages:
        requirement = get_requirement(package)
        package_name_to_search = requirement.name

        if requirement.specifier:
            pinned_package = f"{package_name_to_search}{requirement.specifier}"
        elif requirement.url:
            pinned_package = f"{package_name_to_search} @{requirement.url}"
        else:
            raise Exception(
                f"Invalid package {package} provided. It needs to be pinned to a specific version."
            )

        with fileinput.FileInput("setup.cfg", inplace=True) as setup_file:
            for line in setup_file:
                print(sub(f"{package_name_to_search}.*", pinned_package, line), end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "rc_provider_packages",
        help="Comma separated list of provider packages with their pinned versions to test the the RC."
        " e.g. 'apache-airflow-providers-amazon==4.0.0rc1, apache-airflow-providers-google==8.1.0rc2'",
    )
    args = parser.parse_args()
    rc_provider_packages_list = args.rc_provider_packages.split(",")
    update_setup_cfg(rc_provider_packages_list)
