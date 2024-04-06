from pathlib import Path
from . import LanguageModel
from ..engine import VllmEngine

class Qwen(LanguageModel):
    def __init__(self, models_folder:Path, name:str='Qwen1.5-14B-Chat',
                 use_system_prompt:bool=False, chat_template:str=None, 
                 device:str='cuda', engineType=VllmEngine):
        super().__init__(models_folder=models_folder, name=name, use_system_prompt=use_system_prompt, 
                         chat_template=chat_template, device=device, engineType=engineType)
        # NOTE: needed as the full 32k context overflows the GPU memory
        self.context_size = 8*1024