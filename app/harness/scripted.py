"""Scripted provider for native Inspect tests; no network/inference implementation."""
import inspect
from inspect_ai.model import ModelAPI, ModelOutput, modelapi


@modelapi(name="stonebench-scripted")
class ScriptedProvider(ModelAPI):
    def __init__(self, model_name, base_url=None, api_key=None, config=None, script=None, **kwargs):
        super().__init__(model_name=model_name, base_url=base_url, api_key=None, config=config)
        if script is None:
            raise ValueError("A test script is required")
        self.script = script

    async def generate(self, input, tools, tool_choice, config):
        output = self.script(input, tools, config)
        if inspect.isawaitable(output):
            output = await output
        if not isinstance(output, ModelOutput):
            raise TypeError("Script must supply a ModelOutput with controlled usage (or explicit missing usage)")
        return output
