import logging
import re
import time
from dataclasses import MISSING, dataclass, field, fields, make_dataclass
from pprint import pprint
from typing import Any, Callable, Dict, Optional, Sequence, Union

from github import Github
from github.ContentFile import ContentFile
from typing_extensions import TypedDict

osc_url = "outscale-dev/terraform-provider-outscale"
# url = "hashicorp/terraform-provider-aws"
# url = "terraform-providers/terraform-provider-azurerm"

logging.basicConfig(level=logging.DEBUG)

configuration_block_pattern_aws = re.compile(
    r"^### (?P<name>[a-z_]*) Configuration Block"
)
configuration_block_pattern_azure = re.compile(
    r"`(?P<name>[a-z_]*)` block supports the following:"
)
argument_pattern = re.compile(
    r"^\* `(?P<name>.*)` \- ?(?P<quality>\(Optional\)|\(Required\)) "
)


class ProviderNamespace(Dict[str, Any]):
    def __call__(self, as_property: bool = False) -> Callable:
        def decorator(callback: Callable) -> Callable:
            self[callback.__name__] = property(callback) if as_property else callback
            return callback

        return decorator


provider_namespace = ProviderNamespace()


@provider_namespace()
def get_datasources(self):
    if not hasattr(self, "available_datasources"):
        setattr(
            self,
            "available_datasources",
            (Github().get_repo(self.repository).get_contents("website/docs/d")),
        )
    return self.available_datasources


@dataclass
class Datasource:
    repository: str = field(default="",)
    _data: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __getattr__(self, name: str):
        return recurse_create_dataclass(name.title(), self.get_data(name))

    def get_data(self, name: str):
        if not self._data.get(name):
            content = (
                Github()
                .get_repo(self.repository)
                .get_contents("website/docs/d/" + name + ".html.markdown")
            ).decoded_content.decode()
            self._data[name] = {}
            is_listing_arguments = True
            for line in content.split("\n"):
                logging.debug(line)
                if not is_listing_arguments and line in {
                    "## Arguments Reference",
                    "## Argument Reference",
                }:
                    is_listing_arguments = True

                if is_listing_arguments:
                    logging.debug(line)
                    match = argument_pattern.match(line)
                    if match:
                        argument = match.groupdict()
                        logging.debug(argument["name"])
                        logging.debug(argument.get("quality"))
                        self._data[name]["name"] = argument
        return self._data[name]


@provider_namespace(as_property=True)
def datasources(self) -> Datasource:
    if not hasattr(self, "_datasources"):
        setattr(self, "_datasources", Datasource(self.repository))
    return self._datasources


class Argument(TypedDict, total=False):
    name: str
    quality: str
    _configuration_block: str
    _default_field: Dict[str, Union[str, bool]]


def recurse_create_dataclass(
    name: str,
    input: Dict[str, Union[Dict[str, Argument], Argument]],
    namespace: Optional[Dict[str, Callable]] = None,
):
    logging.info(f"Building dataclass for {name}")
    fields_ = []
    for key, value in input.items():
        if not isinstance(value, dict):
            continue
        optional = value.get("quality") == "(Optional)"
        default_field = value.get("_default_field", {})
        if value.get("_configuration_block"):
            class_name = "".join(x.capitalize() or "_" for x in key.split("_"))
            klass = recurse_create_dataclass(class_name, value)
            field_ = {"default_factory": klass if optional else MISSING}
            field_.update(**default_field)
            fields_.append((key, klass, field(**field_)))
        else:
            field_ = {"default": "" if optional else MISSING}
            field_.update(**default_field)
            fields_.append((key, str, field(**field_)))
    return make_dataclass(name, fields_, namespace=namespace)


def get_provider(repository: str):
    content = (
        Github()
        .get_repo(repository)
        .get_contents("website/docs/index.html.markdown")
        .decoded_content.decode()
    )

    arguments: Dict[str, Argument] = {
        "repository": {
            "name": "repository",
            "_default_field": {"init": False, "default": repository},
        }
    }
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

    return recurse_create_dataclass("Provider", arguments, namespace=provider_namespace)


OSCProvider = get_provider(osc_url)
pprint(fields(OSCProvider))

provider = OSCProvider()
pprint(provider.datasources.get_data("access_key"))
