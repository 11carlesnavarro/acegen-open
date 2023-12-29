import pytest
import torch
from acegen.transforms import BurnInTransform, SMILESReward
from acegen.vocabulary import SMILESVocabulary
from tensordict import TensorDict
from torchrl.modules import GRUModule

tokens = ["(", ")", "1", "=", "C", "N", "O"]


def dummy_reward_function(smiles):
    return [1 for _ in smiles]


def generate_valid_data_batch(
    vocabulary_size: int,
    batch_size: int = 2,
    sequence_length: int = 5,
    max_smiles_length: int = 10,
    smiles_key: str = "SMILES",
    reward_key: str = "reward",
):
    tokens = torch.randint(0, vocabulary_size, (batch_size, sequence_length + 1))
    smiles = torch.randint(
        0, vocabulary_size, (batch_size, sequence_length, max_smiles_length)
    )
    reward = torch.zeros(batch_size, sequence_length, 1)
    done = torch.randint(0, 2, (batch_size, sequence_length + 1, 1), dtype=torch.bool)
    batch = TensorDict(
        {
            "observation": tokens[:, :-1],
            "is_init": done[:, 1:],
            "next": TensorDict(
                {
                    "observation": tokens[:, 1:],
                    "done": done[:, 1:],
                },
                batch_size=[batch_size, sequence_length],
            ),
        },
        batch_size=[batch_size, sequence_length],
    )
    batch.set(("next", reward_key), reward)
    batch.set(("next", smiles_key), smiles)
    return batch


@pytest.mark.parametrize("smiles_key", ["SMILES"])
@pytest.mark.parametrize("reward_key", ["reward", "reward2"])
@pytest.mark.parametrize("batch_size", [2])
@pytest.mark.parametrize("sequence_length", [5])
@pytest.mark.parametrize("max_smiles_length", [10])
def test_reward_transform(
    batch_size, sequence_length, max_smiles_length, smiles_key, reward_key
):
    vocabulary = SMILESVocabulary.create_from_list_of_chars(tokens)
    data = generate_valid_data_batch(
        len(vocabulary),
        batch_size,
        sequence_length,
        max_smiles_length,
        smiles_key,
        reward_key,
    )
    reward_transform = SMILESReward(
        vocabulary=vocabulary,
        reward_function=dummy_reward_function,
        in_keys=[smiles_key],
        out_keys=[reward_key],
    )
    data = reward_transform(data)
    data = data.get("next")
    assert reward_key in data.keys(include_nested=True)
    done = data.get("done").squeeze(-1)
    assert data[done].get(reward_key).sum().item() == done.sum().item()
    assert data[~done].get(reward_key).sum().item() == 0.0


def test_burn_in_transform(
    vocabulary_size: int = 4,
    batch_size: int = 2,
    sequence_length: int = 5,
    max_smiles_length: int = 10,
):
    data = generate_valid_data_batch(
        vocabulary_size,
        batch_size,
        sequence_length,
        max_smiles_length,
    )
    gru = GRUModule(
        input_size=1,
        hidden_size=10,
        batch_first=True,
    )
    burn_in_transform = BurnInTransform(
        modules=[gru],
        burn_in=2,
    )
    import ipdb

    ipdb.set_trace()
    data = burn_in_transform(data)
