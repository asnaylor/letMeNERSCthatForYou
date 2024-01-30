from pathlib import Path
from . import LanguageModel

# Jinja chat template
# found [here](https://github.com/chujiezheng/chat_templates/blob/main/chat_templates/vicuna.jinja)
VICUNA_CHAT_TEMPLATE = """
{% if messages[0]['role'] == 'system' %}
    {% set loop_messages = messages[1:] %}
    {% set system_message = messages[0]['content'].strip() + '\n\n' %}
{% else %}
    {% set loop_messages = messages %}
    {% set system_message = '' %}
{% endif %}
{{ bos_token + system_message }}
{% for message in loop_messages %}
    {% if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}
        {{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}
    {% endif %}
    {% if message['role'] == 'user' %}
        {{ 'USER: ' + message['content'].strip() + '\n' }}
    {% elif message['role'] == 'assistant' %}
        {{ 'ASSISTANT: ' + message['content'].strip() + eos_token + '\n' }}
    {% endif %}
{% endfor %}
{% if add_generation_prompt %}
    {{ 'ASSISTANT:' }}
{% endif %}
"""

class Vicuna(LanguageModel):
    def __init__(self, 
                 models_folder: Path,
                 model_name: str='vicuna-13b-v1.5',
                 device='cuda'):
        super().__init__(models_folder / model_name, device=device)
        self.tokenizer.chat_template = VICUNA_CHAT_TEMPLATE
        self.upper_answer_size = 450
        self.upper_question_size = 200