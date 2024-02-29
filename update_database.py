"""
This script updates the database then stops.
"""
import lmntfy
import argparse
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs_folder", default="./data/nersc_doc/docs", type=Path, help="path to the NERSC documentation folder")
    parser.add_argument("--database_folder", default="./data/database", type=Path, help="path to the database saving folder") 
    parser.add_argument("--models_folder",default="../models",type=Path, help="path to the folder containing all the models")
    args = parser.parse_args()
    return args

def main():
    # process command line arguments
    args= parse_args()
    docs_folder = args.docs_folder
    database_folder = args.database_folder
    models_folder = args.models_folder

    # load the database and updates it if needed
    llm = lmntfy.models.llm.Default(models_folder, device='cpu')
    embedder = lmntfy.models.embedding.SBERTEmbedding(models_folder)
    database = lmntfy.database.Default(llm, embedder, docs_folder, database_folder, update_database=True)
    print("Done!")

if __name__ == "__main__":
    main()
