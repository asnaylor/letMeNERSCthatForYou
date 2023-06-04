# Let Me NERSC that For You

This is a custom-made documentation Chatbot based on the [NERSC documentation](https://docs.nersc.gov/).

## Goals

This bot is not made to replace the documentation but rather to improve information discoverability.

* Being able to answer questions on NERSC with up-to-date, *sourced*, answers,
* make it fairly easy to switch the underlying models (embeddings and LLM) such that it can be run on-premise,
* have a user-facing web-based user interface.

## Installation

**TODO**
- clone the repo
- get an api key
- get the dependency in your environement (openai, tiktoken, faiss-cpu)

## Usage

**TODO:**
- put the API key in environement
- run lmntfy.py

## TODO

Q&A:
- improve source answer setup
- have a chat (back and forth) set-up?
- harden model against error (input size, model failure, etc: if retying is not enough then we should return an error message to the user)

Model:
- have a Vicuna based alternative setup

Embeddings:
- get SBERT embeddings working as a viable alternative

Database:
- get a google search based retrieval set-up (nothing stored, instead we look up information online).
- add input preprocessing to turn question into something closer to the target

UI:
- command line UI
- web UI
