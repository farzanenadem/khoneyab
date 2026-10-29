import operator

from typing_extensions import Annotated, Any, TypedDict, Union


class Metadata(TypedDict):
    key: str
    value: Any


class DebugInfo(TypedDict):
    node_name: str
    output: Union[list[Any], Any]
    metadata: list[Metadata]


class BaseAgentState(TypedDict):
    debug_info: Annotated[list[DebugInfo], operator.add]
