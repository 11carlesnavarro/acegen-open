import numpy as np

from acegen.vocabulary.base import Tokenizer, Vocabulary


class SMILESVocabulary(Vocabulary):
    """A class for handling encoding/decoding from SMILES to an array of indices.

    Args:
        start_token (str, optional): The start token. Defaults to "GO".
        start_token_index (int, optional): The index of the start token. Defaults to 0.
        end_token (str, optional): The end token. Defaults to "EOS".
        end_token_index (int, optional): The index of the end token. Defaults to 1.
        max_length (int, optional): The maximum length of the SMILES string. Defaults to 140.
        tokenizer (Tokenizer, optional): A tokenizer to use for tokenizing the SMILES. Defaults to None.
            Any class that implements the tokenize and untokenize methods can be used.

    Examples:
        >>> from acegen.vocabulary import SMILESVocabulary
        >>> chars = ["(", ")", "1", "=", "C", "N", "O"]

        >>> vocabulary = SMILESVocabulary()
        >>> vocabulary.add_characters(chars)

        >>> tokens_dict = dict(zip(chars + ["EOS", "GO"], range(len(chars) + 2)))
        >>> vocabulary = SMILESVocabulary.create_from_dict(tokens_dict)
    """

    def __init__(
        self,
        start_token: str = "GO",
        start_token_index: int = 0,
        end_token: str = "EOS",
        end_token_index: int = 1,
        max_length: int = 140,
        tokenizer: Tokenizer = None,
    ):
        self.start_token = start_token
        self.end_token = end_token
        self.special_tokens = [end_token, start_token]
        special_indices = [end_token_index, start_token_index]
        self.additional_chars = set()
        self.chars = self.special_tokens
        self.vocab_size = len(self.chars)
        self.vocab = dict(zip(self.chars, special_indices))
        self.reversed_vocab = {v: k for k, v in self.vocab.items()}
        self.max_length = max_length
        self.tokenizer = tokenizer

    def encode(self, smiles):
        """Takes a list of characters (eg '[NH]') and encodes to array of indices."""
        if self.tokenizer is None:
            raise RuntimeError(
                "Tokenizer not set. Please set a valid tokenizer first."
                "Any class that implements the Tokenizer interface can be used."
            )

        char_list = self.tokenizer.tokenize(smiles)
        smiles_matrix = np.zeros(len(char_list), dtype=np.float32)
        for i, char in enumerate(char_list):
            smiles_matrix[i] = self.vocab[char]
        return smiles_matrix

    def decode(self, encoded_smiles, ignore_indices=()):
        """Takes an array of indices and returns the corresponding SMILES."""
        chars = []
        for i in encoded_smiles:
            if i in ignore_indices:
                continue
            if i == self.vocab[self.start_token]:
                continue
            if i == self.vocab[self.end_token]:
                break
            chars.append(self.reversed_vocab[i])
        smiles = "".join(chars)
        smiles = smiles.replace("L", "Cl").replace("R", "Br")
        return smiles

    def add_characters(self, chars):
        """Adds characters to the vocabulary."""
        for char in chars:
            if char not in self.chars:
                self.additional_chars.add(char)
        char_list = list(self.additional_chars)
        char_list.sort()
        self.chars = char_list + self.special_tokens
        self.vocab_size = len(self.chars)
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.reversed_vocab = {v: k for k, v in self.vocab.items()}

    def __len__(self):
        return len(self.chars)

    def __str__(self):
        return "Vocabulary containing {} tokens: {}".format(len(self), self.chars)

    @classmethod
    def create_from_smiles(
        cls,
        smiles_list: list[str],
        tokenizer: Tokenizer,
        start_token: str = "GO",
        start_token_index: int = 0,
        end_token: str = "EOS",
        end_token_index: int = 1,
        max_length: int = 140,
    ):
        """Creates a vocabulary for the SMILES syntax."""
        vocabulary = cls(
            start_token=start_token,
            start_token_index=start_token_index,
            end_token=end_token,
            end_token_index=end_token_index,
            max_length=max_length,
            tokenizer=tokenizer,
        )
        tokens = set()
        for smi in smiles_list:
            tokens.update(vocabulary.tokenizer.tokenize(smi))
        vocabulary = cls()
        vocabulary.add_characters(sorted(tokens))
        return vocabulary

    @classmethod
    def create_from_dict(
        cls,
        vocab: dict[str, int],
        start_token: str = "GO",
        end_token: str = "EOS",
        max_length: int = 140,
        tokenizer: Tokenizer = None,
    ):
        """Creates a vocabulary from a dictionary.

        The dictionary should map characters to indices and should include the start and end tokens.
        """
        vocabulary = cls(
            start_token=start_token,
            end_token=end_token,
            max_length=max_length,
            tokenizer=tokenizer,
        )
        vocabulary.vocab_size = len(vocab)
        vocabulary.vocab = vocab
        vocabulary.reversed_vocab = {v: k for k, v in vocabulary.vocab.items()}
        vocabulary.chars = list(vocabulary.vocab.keys())
        vocabulary.special_tokens = [end_token, start_token]
        vocabulary.additional_chars = {
            char for char in vocabulary.chars if char not in vocabulary.special_tokens
        }
        return vocabulary
