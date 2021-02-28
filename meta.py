import logging
from pprint import pprint
from typing import Any, Dict

from github import Github

url = "outscale-dev/terraform-provider-outscale"
# url = "hashicorp/terraform-provider-aws"
# url = "terraform-providers/terraform-provider-azurerm"

logging.basicConfig(level=logging.INFO)

import re
from dataclasses import MISSING, field, make_dataclass

configuration_block_pattern_aws = re.compile(
    r"^### (?P<name>[a-z_]*) Configuration Block"
)
configuration_block_pattern_azure = re.compile(
    r"`(?P<name>[a-z_]*)` block supports the following:"
)
argument_pattern = re.compile(
    r"^\* `(?P<name>.*)` \- ?(?P<quality>\(Optional\)|\(Required\)) "
)


def recurse_create_dataclass(name: str, input: Dict[str, Dict[str, Any]]):
    logging.info(f"Building dataclass for {name}")
    fields_ = []
    for key, value in input.items():
        if not isinstance(value, dict):
            continue
        optional = value.get("quality") == "(Optional)"
        if value.get("_configuration_block"):
            class_name = "".join(x.capitalize() or "_" for x in key.split("_"))
            klass = recurse_create_dataclass(class_name, value)
            fields_.append(
                (key, klass, field(default_factory=klass if optional else MISSING))
            )
        else:
            fields_.append((key, str, field(default="" if optional else MISSING)))
    return make_dataclass(name, fields_)


def get_provider(provider: str):
    content = (
        Github()
        .get_repo(provider)
        .get_contents("website/docs/index.html.markdown")
        .decoded_content.decode()
    )

    arguments = {}
    is_listing_arguments = False
    is_listing_conf_blocks = False
    block_name = ""

    for line in content.split("\n"):
        logging.debug(line)
        if not is_listing_arguments and line in {
            "## Arguments Reference",
            "## Argument Reference",
        }:
            is_listing_arguments = True

        if is_listing_arguments:
            match = argument_pattern.match(line)
            if match:
                argument = match.groupdict()
                logging.debug(argument["name"])
                logging.debug(argument.get("quality"))
                arguments[argument["name"]] = argument

        block_match = configuration_block_pattern_aws.match(
            line
        ) or configuration_block_pattern_azure.match(line)
        if block_match:
            is_listing_arguments = False
            is_listing_conf_blocks = True
            block_name = block_match.groupdict()["name"]
            logging.debug("---")
            logging.debug(block_name)
            arguments[block_name]["_configuration_block"] = True

        if is_listing_conf_blocks:
            match = argument_pattern.match(line)
            if match:
                argument = match.groupdict()
                logging.debug(argument["name"])
                logging.debug(argument.get("quality"))
                arguments[block_name][argument["name"]] = argument

    pprint(arguments)

    return recurse_create_dataclass("Provider", arguments)


Provider = get_provider(url)
# pprint(fields(Provider))
