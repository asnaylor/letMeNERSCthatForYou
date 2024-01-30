import os
from enum import Enum, auto
from abc import ABC, abstractmethod
from copy import copy
from typing import List, Dict
from ...database.document_loader import Chunk
from transformers import PreTrainedTokenizer
import outlines
from outlines.models.transformers import Transformer
from outlines.generate import SequenceGenerator

# NOTE: this is needed as the initialization of outlines's caching system will try to write to $HOME/.chache/outlines
os.environ['OUTLINES_CACHE_DIR'] = os.environ.get('TMPDIR')
# disables caching
outlines.disable_cache()

#----------------------------------------------------------------------------------------
# PROMPTS

# Basic chat prompt
CHAT_PROMPT_SYSTEM = """
You are a member of the NERSC supercomputing center's support staff answering a user's questions.
Use an unbiased and journalistic tone. \
Only cite the most relevant results that answer the user's questions accurately. \
Try and be careful not to go off-topics.
"""

# prompt to answer a question
# NOTE: 
# * we do a single shot prompt (with an example answer) to ensure proper formating of the answer at the price of a few tokens
# * note that the end of the prompt is ready to accomodate some chunks of information
ANSWERING_PROMPT="""
You are a member of the NERSC supercomputing center's support staff.
Generate a comprehensive and informative answer for a given question solely based on the provided information (URL and Extract).
You must only use information from the provided search results. \
Use an unbiased and journalistic tone. \
Combine search results together into a coherent answer. \
Only cite the most relevant results that answer the question accurately. \
Try and be careful not to go off-topics. \
After providing the answer, list the URLs of the information sources you used in a `References:` section, sorted from most to least relevant. Include ONLY the URLs that are directly relevant to the answer.

### Example Answer Format:

To optimize your code for CPU usage at NERSC, it's crucial to focus on vectorization and parallelization. Vectorization allows your code to process multiple data points with a single instruction, effectively reducing the time your code takes to run through large datasets. Parallelization, on the other hand, involves dividing your code into multiple tasks that can be processed simultaneously, maximizing the use of available CPU resources. Combining these two strategies can lead to significant improvements in your code's performance on NERSC systems.

References:
* <https://docs.nersc.gov/cpu-optimization>
* <https://docs.nersc.gov/parallel-computing>

### Information Sources:
"""

#----------------------------------------------------------------------------------------
# MODEL ABSTRACTION

class LanguageModel(ABC):
    """
    Abstraction over large language models
    Built on top of the [Outlines](https://github.com/outlines-dev/outlines) library

    Message format:
        we expect messages to have a "role" ("system", "user", or "assistant") as well as a "content" field
        all "system" messages will be concatenated and put at the beginning of the conversation
        if the conversation is too long to fit the answer, messages with a "relevancy" field will be dropped (starting with lowest relevancy) until it fits
    """
    def __init__(self, pretrained_model_name_or_path:str, device='cuda'):
        self.pretrained_model_name_or_path = str(pretrained_model_name_or_path)
        self.model: Transformer = outlines.models.transformers(self.pretrained_model_name_or_path, device=device)
        self.tokenizer: PreTrainedTokenizer = self.model.tokenizer.tokenizer # get the Transformer Tokenizer for chattemplating purposes
        self.context_size = self.model.model.config.max_position_embeddings
        self.upper_answer_size = None # needs to be filled per tokenizer
        self.upper_question_size = None # needs to be filled per tokenizer
        # generators
        self.base_generator = outlines.generate.text(self.model)

    def count_tokens(self, text:str) -> int:
        """
        Counts the number of tokens in a given string.
        """
        tokens = self.tokenizer.encode(text, return_tensors='pt')
        token_number = tokens.size(-1)
        return token_number

    def _clean_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Given a conversation:
        * merge all system messages into the first message
        * ensure they alternate properly between user and assistant (can be caused by relevancy problems)
          by dropping eroneous messages silently
        """
        # gets a system message
        if (len(messages) < 1) or (messages[0]['role'] != "system"):
            raise RuntimeError("Your messages do not start with a system prompt!")
        else:
            system_message = copy(messages[0])
            messages = messages[1:]

        # accumulate system messages
        nonsystem_messages = []
        for message in messages:
            if (message['role'] == "system"):
                # add content to the system message
                system_message['content'] += message['content']
            else:
                # add message to result
                nonsystem_messages.append(message)

        # ensure alternance of user-assistant messages in non-system messages
        result = [system_message]
        next_is_user = True
        for message in nonsystem_messages:
            is_user = (message['role'] == 'user')
            if (next_is_user and is_user) or ((not next_is_user) and (not is_user)):
                result.append(message)
                next_is_user = not next_is_user
        return result

    def _drop_lowest_priority_message(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Finds the message with the lowest relevancy score and drops it from the conversation.
        If no message can be cut, returns None.
        """
        # Find the index of the least relevant message, if any
        least_relevant_index = None
        least_relevancy = float('inf')
        for i, message in enumerate(messages):
            if ('relevancy' in message) and (message['relevancy'] < least_relevancy):
                least_relevancy = message['relevancy']
                least_relevant_index = i

        # returns
        if least_relevant_index is None:
            # no message can be cut, return None
            return None
        else:
            # pop lowest relevancy message
            messages.pop(least_relevant_index)
            return messages

    def apply_chat_template(self, messages: List[Dict[str, str]], nb_tokens_max:int=None) -> str:
        """
        Takes a list of messages and applies the model's chat template.

        NOTE:
        - drops optional messages until the result fits in the given size
        - merge all systems messages into the first message
        """
        # fails hard if the tokeniser does not have a chat_template
        if self.tokenizer.chat_template is None:
            raise RuntimeError(f"Your tokeniser ({type(self.tokenizer)}) of choice does not have a chat_template. See [this repository](https://github.com/chujiezheng/chat_templates/tree/main) for common options.")
        
        # merge system messages (in case there is more than one)
        merged_messages = self._clean_messages(messages)
        
        # turns the conversation into a single string
        try:
            output_string = self.tokenizer.apply_chat_template(merged_messages, add_generation_prompt=True, tokenize=False)
        except Exception as e:
            raise RuntimeError(f"Failed to apply chat templates with error '{e}'. Roles are: {[m['role'] for m in merged_messages]}") from e

        # drop optional messages if needed
        if (nb_tokens_max is not None) and (self.count_tokens(output_string) > nb_tokens_max):
            shorten_messages = self._drop_lowest_priority_message(messages)
            if shorten_messages is not None:
                # if we could drop a message
                return self.apply_chat_template(shorten_messages, nb_tokens_max)
            
        return output_string

    def generate(self, text:str, verbose:bool=False, generator:SequenceGenerator=None) -> str:
        """
        Query the model and get a response.

        Args:
            input_data (str): the text prompt
            verbose (bool): should we print debug information? (defaults to False)
            generator (SequenceGenerator): outline generator and the counstraints that go with it

        Returns:
            str: The generated response from the model.
        """
        # picks a generator, defaults to basic text completion
        if generator is None:
            generator = self.base_generator

        # runs the generator
        output = generator(text)

        # debugging information
        if verbose:
            print(text)
            print(output)

        return output

    def extract_question(self, previous_messages:List[Dict], verbose=False) -> str:
        """
        Tries to extract the last question.
        """
        # builds the messages
        system_message = {"role": "system", "content": CHAT_PROMPT_SYSTEM}
        formatted_discussion = [{**message, 'relevancy': i} for (i,message) in enumerate(previous_messages)]
        messages = [system_message] + formatted_discussion
        # builds the base prompt
        prompt = self.apply_chat_template(messages, nb_tokens_max=self.context_size-self.upper_question_size)
        # prime the model to extract the question
        prompt_question_extraction = prompt + 'If I understand you clearly, your question is: "'
        question = self.base_generator(prompt_question_extraction, stop_at='"')[:-1]
        print(f"DEBUGGING: question:'{question}'")
        return question

    def chat(self, discussion:List[Dict[str, str]], chunks:List[Chunk], verbose=False) -> str:
        """
        Chat with the model given the previous messages
        and relevant chunks of the documentation to enrich the chat.
        """
        # builds the messages
        nb_messages_minimum = 3 # keep at least that many messages (when possible)
        nb_relevant_messages = len(chunks) + max(0, len(discussion)-nb_messages_minimum)
        system_message = {"role": "system", "content": ANSWERING_PROMPT}
        # formats the chunks
        chunks_messages = [{"role": "system", "content": f"\n{chunk.to_markdown()}", "relevancy": (nb_relevant_messages-i)} for (i,chunk) in enumerate(chunks)]
        # formats the discussion
        if len(discussion) <= nb_messages_minimum:
            discussion_messages = discussion
        else:
            # extracts the last 3 messages, they will stay untouched
            discussion_end = discussion[-3:]
            # extract the first messages and add a relevancy to them
            discussion_start = discussion[:-3]
            discussion_start = [{**message, 'relevancy': i} for (i,message) in enumerate(discussion_start)]
            # assemble the discussion
            discussion_messages = discussion_start + discussion_end
        # assemble the messages
        messages = [system_message] + chunks_messages + discussion_messages

        # turns the messages into a prompt
        prompt = self.apply_chat_template(messages, nb_tokens_max=self.context_size-self.upper_answer_size)

        # generates an answer in two part to ensure it follows our prefered format
        # 1. body of the answer
        answer_body = self.base_generator(prompt, stop_at=["References:", "Sources:"])
        answer_body = answer_body.replace("Sources:", "References:") # normalize reference format
        if not "References:" in answer_body: 
            if any(substr in answer_body for substr in ["\n * [", "\n * <", "\n* [", "\n* <"]):
                # there are already references in the answer, exit
                return answer_body
            else:
                # no references found, let's add some
                answer_body += "\n\nReferences:"
        # 2. references, priming the model to follow our prefered format
        prompt_extended = prompt + answer_body + "\n * <https://docs.nersc.gov"
        answer_references = self.base_generator(prompt_extended, stop_at="\n\n")
        # assemble the answer
        answer = answer_body + "\n * <https://docs.nersc.gov" + answer_references
        return answer

from .llama2 import Llama2
from .vicuna import Vicuna
from .mistral import Mistral
from .zephyr import Zephyr