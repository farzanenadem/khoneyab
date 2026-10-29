import yaml
from phoenix.otel import register
from yaml.loader import SafeLoader

api_args = None
with open("configs/api_config.yaml", "rb") as config_file:
    api_args = yaml.load(config_file, Loader=SafeLoader)

tracer_provider = register(
    endpoint=api_args["trace_url"], project_name=api_args["trace_name"], auto_instrument=True
)
