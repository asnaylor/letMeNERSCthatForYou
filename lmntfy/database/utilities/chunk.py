import re

class Chunk:
    def __init__(self, url:str, content:str):
        self.url = url
        self.content = content.strip()

    def __str__(self):
        """turns a chunk into a string representation suitable for usage in a prompt"""
        return f"URL: {self.url}\n\n{self.content}"

    def to_markdown(self):
        """turns a chunk into a markdown representation suitable for usage in a prompt"""
        markdown_content = "\n".join([f"> {line}" for line in self.content.split('\n')])
        return f"Source URL: <{self.url}>\n\nExtract:\n{markdown_content}\n\n---\n"

    def to_dict(self):
        return {
            'url': self.url,
            'content': self.content
        }

    def __eq__(self, other):
        if not isinstance(other, Chunk):
            return False
        return (self.url == other.url) and (self.content == other.content)

    def __hash__(self):
        return hash((self.url, self.content))

    @staticmethod
    def from_dict(data):
        return Chunk(data['url'], data['content'])