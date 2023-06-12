import json
import os
import numpy as np
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from .vector_database import VectorDatabase, FaissVectorDatabase
from ..models.embedding import Embedding
from ..models.llm import LanguageModel
from .document_loader import Chunk, chunk_file


#------------------------------------------------------------------------------
# FILE

class File:
    def __init__(self, creation_date, vector_database_indices=None):
        # when was the file last modified
        self.creation_date = creation_date
        # list of all database indices
        self.vector_database_indices = vector_database_indices or list()

    def add_index(self, vector_database_index):
        self.vector_database_indices.append(vector_database_index)

    def to_dict(self):
        return {
            'creation_date': self.creation_date.isoformat(),
            'vector_database_indices': self.vector_database_indices
        }

    @staticmethod
    def from_dict(data):
        creation_date = datetime.fromisoformat(data['creation_date'])
        vector_database_indices = data['vector_database_indices']
        return File(creation_date, vector_database_indices)

#------------------------------------------------------------------------------
# DATABASE

class Database:
    def __init__(self, llm:LanguageModel, embedder:Embedding,
                       documentation_folder:Path, database_folder:Path, 
                       vector_database_class=FaissVectorDatabase, 
                       min_chunks_per_query=3, update_database=True):
        self.embedder = embedder
        self.vector_database = vector_database_class(embedder.embedding_length)
        # maximum size of each chunk
        # we leave space for two additional chunks, representing the prompt and the model's answer
        self.max_tokens_per_chunk = llm.context_size / (min_chunks_per_query + 2)
        # the token counting function
        self.token_counter = llm.token_counter
        # dictionary of all files
        # file_path -> File
        self.files: Dict[Path, File] = dict()
        # dictionary of all chunk
        # vector_database_index -> Chunk
        self.chunks: Dict[int, Chunk] = dict()
        # loads the database from file if possible
        self.documentation_folder = documentation_folder
        self.database_folder = database_folder
        self.load(update_database=update_database, verbose=True)
    
    def get_closest_chunks(self, input_text: str, k: int = 3) -> List[Chunk]:
        if len(self.chunks) <= k: return list(self.chunks.values())
        # Generate input text embedding
        input_embedding = np.array([self.embedder.embed(input_text)], dtype='float32')
        # Query the vector databse
        indices = self.vector_database.get_closest(input_embedding, k)
        # Return the corresponding chunks
        return [self.chunks[i] for i in indices]

    def remove_file(self, file_path):
        """Removes a file's content from the Database"""
        file = self.files[file_path]
        indices_to_remove = file.vector_database_indices
        # remove file chunks from chunks
        for index in indices_to_remove:
            del self.chunks[index]
        # remove embeddings from vector database
        self.vector_database.remove_several(indices_to_remove)
        # remove file from files
        del self.files[file_path]

    def add_file(self, file_path):
        """Add a file's content to the database"""
        # slice file into chunks
        chunks = chunk_file(file_path, self.token_counter, self.max_tokens_per_chunk)
        # save chunks to memory
        file_update_date = datetime.fromtimestamp(file_path.stat().st_mtime)
        file = File(creation_date=file_update_date)
        for chunk in chunks:
            # embed chunk
            embedding = np.array([self.embedder.embed(chunk.content)], dtype='float32')
            # put chunks into the database
            chunk_index = self.vector_database.add(embedding)
            # save information on chunk
            file.add_index(chunk_index)
            self.chunks[chunk_index] = chunk
        self.files[file_path] = file

    def update(self, verbose=False):
        """Goes over the documentation and insures that we are up to date then saves the result."""
        # removes files that do not exist anymore or are out of date
        existing_files = list(self.files.items())
        for file_path, file in tqdm(existing_files, disable=not verbose, desc="Removing old files"):
            if (not file_path.exists()) or (datetime.fromtimestamp(file_path.stat().st_mtime) > file.creation_date):
                self.remove_file(file_path)
        # add new files
        current_files = [Path(root) / file for root, dirs, files in os.walk(self.documentation_folder) for file in files]
        if len(current_files) == 0:
            raise RuntimeError(f"ERROR: the documentation folder '{self.documentation_folder}' is empty or does not exist.")
        for file_path in tqdm(current_files, disable=not verbose, desc="Loading new files"):
            if not file_path in self.files:
                self.add_file(file_path)
        # save resulting database
        self.save()

    def exists(self):
        """returns True if the database already exists on disk"""
        files_file = self.database_folder / 'files.json'
        chunks_file = self.database_folder / 'chunks.json'
        return self.database_folder.exists() and self.vector_database.exists(self.database_folder) and files_file.exists() and chunks_file.exists()

    def load(self, update_database=True, verbose=False):
        if self.exists():
            # load the vector database
            self.vector_database.load(self.database_folder)
            # load the files info
            with open(self.database_folder / 'files.json', 'r') as f:
                files_dict = json.load(f)
                self.files = {Path(k): File.from_dict(v) for k, v in files_dict.items()}
            # load the chunks
            with open(self.database_folder / 'chunks.json', 'r') as f:
                chunks_dict = json.load(f)
                self.chunks = {int(k): Chunk.from_dict(v) for k, v in chunks_dict.items()}
        elif verbose:
            print(f"Warning: '{self.database_folder}' or its content does not currently exist. The database will be created from scratch.")
        # updates the database to the latest documentation
        if update_database:
            self.update(verbose=verbose)

    def save(self):
        # insures that the saving folder exists
        self.database_folder.mkdir(parents=True, exist_ok=True)
        # saves the vector database
        self.vector_database.save(self.database_folder)
        # saves the files info
        with open(self.database_folder / 'files.json', 'w') as f:
            files_dict = {str(k): v.to_dict() for k, v in self.files.items()}
            json.dump(files_dict, f)
        # saves the chunks
        with open(self.database_folder / 'chunks.json', 'w') as f:
            chunks_dict = {k: v.to_dict() for k, v in self.chunks.items()}
            json.dump(chunks_dict, f)
