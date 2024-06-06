from pathlib import Path
from typing import List, Dict, Tuple
from ..chunk import Chunk
from . import SearchEngine
from whoosh.index import FileIndex, exists_in, create_in, open_dir
from whoosh.fields import Schema, ID, TEXT, KEYWORD
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.analysis import StemmingAnalyzer
from whoosh.scoring import WeightingModel, BM25F

#------------------------------------------------------------------------------
# UTILITIES

# Define the schema for our Chunk index
# somewhat inspired by this: https://git.charlesreid1.com/charlesreid1/markdown-search
# NOTE: an LLM keyword extraction system might be interesting to get a better index
CHUNK_SCHEMA = Schema(
    id=ID(stored=True, unique=True), # will be used to delete old chunks
    headlines=KEYWORD(analyzer=StemmingAnalyzer(), field_boost=5.0), # markdown titles, more important
    content=TEXT(phrase=False, analyzer=StemmingAnalyzer(), field_boost=1.0) # actual text
)

def extract_headlines(content: str) -> str:
    """
    Produces a string that only contains the headlines of a markdown file.
    (the formulla also applies to shell comments which is acceptable)
    
    Parameters:
    - content: A string representing the content of a markdown file.
    
    Returns:
    - A string containing only the headlines from the input markdown content,
      each followed by a newline character.
    """
    # keep only the headline lines
    headlines = [line.strip() for line in content.split('\n') if line.startswith('#')]
    # Join the headlines with newline characters and return
    return '\n'.join(headlines)

#------------------------------------------------------------------------------
# SEARCH

class KeywordSearch(SearchEngine):
    """
    Classic keyword-based (BM25F) search.
    Based on [Whoosh](https://whoosh.readthedocs.io/en/latest/index.html).
    WARNING: as the index update requires modifications on file, it cannot be updated from a compute node.
    """
    def __init__(self, scoring:WeightingModel=BM25F(B=0.0), name:str='keyword'):
        """
        score (WeightingModel): function used to score hits, defaults to BM25F(B=0.0), B=0 means no penality to document length
        """
        # whoosh index
        self.index: FileIndex = None # created on load
        # function used to score hits
        self.scoring: WeightingModel = scoring
        # init parent
        super().__init__(name=name)

    def add_several_chunks(self, chunks: dict[int,Chunk]):
        """
        Adds several chunks with the given indices.
        """
        writer = self.index.writer()
        for (chunk_id, chunk) in chunks:
            # gets the headlines from the file
            headlines = extract_headlines(chunk.content)
            # add chunk content to the index
            writer.add_document(id=str(chunk_id), headlines=headlines, content=chunk.content)
        writer.commit()

    def remove_several_chunks(self, chunk_indices: List[int]):
        """
        Removes several chunks from the search engine.
        """
        writer = self.index.writer()
        for chunk_id in chunk_indices:
            # remove chunk from the index
            writer.delete_by_term(fieldname='id', text=str(chunk_id))
        writer.commit()
    
    def get_closest_chunks(self, input_text: str, chunks:Dict[int,Chunk], k: int) -> List[Tuple[float,int]]:
        """
        Returns the (score,chunk_id) of the closest chunks, from best to worst
        """
        # does a search in the index
        result = []
        with self.index.searcher(weighting=self.scoring) as searcher:
            # match all documents that contains at least one of the terms
            query = MultifieldParser(['content','headlines'], schema=self.index.schema, group=OrGroup).parse(input_text)
            for hit in searcher.search(query, limit=k):
                result.append((hit.score, hit['id']))
        return result
    
    def save(self, database_folder:Path):
        """
        Save the search engine on file.
        """
        # NOTE: nothing to do as `writer.commit` already takes care of saving
        return

    def load(self, database_folder:Path):
        """
        Loads the search engine from file.
        """
        if exists_in(database_folder):
            # the index already exists
            self.index = open_dir(self.database_folder)
        else:
            # creates a new index
            self.index = create_in(database_folder, CHUNK_SCHEMA)
