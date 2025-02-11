from typing import AsyncGenerator
from enum import Enum
from pydantic import BaseModel, Field
import requests
from openai import AsyncOpenAI
import json

class State(Enum):
    EMPTY = 1
    THINKING = 2
    CONTENT = 3


class Pipe:
    class Valves(BaseModel):
        NAME_PREFIX: str = Field(
            default="tencentcloud/",
            description="Prefix to be added before model names.",
        )
        BASE_URL: str = Field(
            default="https://api.lkeap.cloud.tencent.com/v1",
            description="Base URL for accessing TencentCloud API endpoints.",
        )
        API_KEY: str = Field(
            default="",
            description="API key for authenticating requests to the TencentCloud API.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        if self.valves.API_KEY:
            try:
                if not self.valves.API_KEY:
                    raise Exception("no api key")
                headers = {
                    "Authorization": f"Bearer {self.valves.API_KEY}",
                    "Content-Type": "application/json",
                }

                r = requests.get(
                    f"{self.valves.BASE_URL}/models", headers=headers
                )
                models = r.json()

                return [
                    {
                        "id": model["id"],
                        "name": f'{self.valves.NAME_PREFIX}{model.get("name", model["id"])}',
                    }
                    for model in models["data"]
                ]
            except Exception as e:
                return [
                    {
                        "id": "error",
                        "name": "Error fetching models. Please check your API Key."
                    },
                ]
        else:
            return [
                {
                    "id": "error",
                    "name": "API Key not provided.",
                },
            ]

    @staticmethod
    def generate_json_error(err_msg:str):
        return '''```json
{{
  "error": "{}",
}}
```\n'''.format(err_msg)

    @staticmethod
    def get_model_id(pipe_id: str) -> str:
        if "." in pipe_id:
            _,pipe_id= pipe_id.split(".", 1)
        return pipe_id

    async def pipe(self, body: dict) ->AsyncGenerator[str, None]:
        state = State.EMPTY
        try:
            async with (AsyncOpenAI(api_key=self.valves.API_KEY, base_url=self.valves.BASE_URL) as client):
                chat_completion = await client.chat.completions.create(
                    model=self.get_model_id(body["model"]),
                    messages=body["messages"],
                    stream=True
                )
                response = chat_completion.response
                line_iter = response.aiter_lines()
                first_line = await line_iter.__anext__()
                try:
                    first_line_json = json.loads(first_line)
                    if 'error' in first_line_json and 'message' in first_line_json['error']:
                        yield self.generate_json_error(first_line_json['error']['message'])
                        return
                except:
                    pass

                decoder = client._make_sse_decoder()
                decoder.decode(first_line)
                async for line in line_iter:
                    sse = decoder.decode(line)
                    if not sse:
                        continue
                    if sse.data.startswith("[DONE]"):
                        break
                    sse_json = sse.json()
                    if 'choices' in sse_json and isinstance(sse_json['choices'], list) \
                        and len(sse_json['choices']) > 0 and 'delta' in sse_json['choices'][0]:
                        delta = sse_json['choices'][0]['delta']
                        if 'reasoning_content' in delta:
                            reasoning_content = delta['reasoning_content']
                            if reasoning_content:
                                if state != State.THINKING:
                                        state = State.THINKING
                                        yield "<think>"
                                yield reasoning_content
                        if 'content' in delta:
                            content = delta['content']
                            if content:
                                if state == State.THINKING:
                                        state = State.CONTENT
                                        yield "</think>"
                                yield content
        except Exception as e:
            yield self.generate_json_error(str(e))
        return


if __name__ == '__main__':
    async def main():
        body = {
            "model": "test.deepseek-r1",
            "messages": [
                  {
                    "role": "user",
                    "content": "你好"
                  }
                ]
        }
        pipe = Pipe()
        async for item in pipe.pipe(body):
            print(item, end="")

    import asyncio
    asyncio.run(main())
