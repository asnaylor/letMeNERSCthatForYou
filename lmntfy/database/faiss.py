import faiss
import json
import numpy as np
from pathlib import Path
from typing import List
from . import Database
from ..models import LanguageModel, Embedding

class FaissDatabase(Database):
    def __init__(self, llm: LanguageModel, embedder: Embedding,
                 documentation_folder: Path, database_folder: Path,
                 min_chunks_per_query=3, update_database=True, name='faiss'):
        # vector database that will be used to store the vectors
        raw_index = faiss.IndexFlatIP(embedder.embedding_length)
        # index on top of the database to support addition and deletion by id
        self.index = faiss.IndexIDMap(raw_index)
        self.current_id = 0
        # conclude the initialisation
        super().__init__(llm, embedder, documentation_folder, database_folder, min_chunks_per_query, update_database, name)

    def _index_add(self, embedding: np.ndarray) -> int:
        assert (embedding.size == self.embedding_length), "Invalid shape for embedding"
        self.index.add_with_ids(embedding, np.array([self.current_id], dtype=np.int64))
        self.current_id += 1
        return self.current_id - 1  # Return the ID of the added vector

    def _index_remove_several(self, indices: List[int]):
        self.index.remove_ids(np.array(indices, dtype=np.int64))

    def _index_get_closest(self, input_embedding: np.ndarray, k=3) -> List[int]:
        assert (input_embedding.size == self.embedding_length), "Invalid shape for input_embedding"
        _, indices = self.index.search(input_embedding, k)
        return indices.flatten().tolist()

    def exists(self) -> bool:
        """returns True if the database already exists on disk"""
        index_file = self.database_folder / 'index.faiss'
        database_data_file = self.database_folder / 'faiss_vector_database.json'
        return super().exists() and index_file.exists() and database_data_file.exists()

    def save(self):
        # first save the rest of the database, ensuring the folder exists
        super().save()
        # saves the index
        index_path = self.database_folder / 'index.faiss'
        faiss.write_index(self.index, str(index_path))
        # saves the database data
        with open(self.database_folder / 'faiss_vector_database.json', 'w') as f:
            database_data = {'current_id': self.current_id}
            json.dump(database_data, f)

    def load(self, update_database=True, verbose=False):
        if self.exists():
            # load the index
            index_path = self.database_folder / 'index.faiss'
            self.index = faiss.read_index(str(index_path))
            # load the database_data
            with open(self.database_folder / 'faiss_vector_database.json', 'r') as f:
                database_data = json.load(f)
                self.current_id = int(database_data['current_id'])
        # loads the rest of the database and optionaly updates it
        super().load(update_database=update_database, verbose=verbose)