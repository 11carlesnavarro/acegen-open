import torch
import torch.nn as nn
from tensordict.nn import TensorDictModule
from torchrl.envs import ExplorationType
from torchrl.modules import ProbabilisticActor


class MultiGRU(nn.Module):
    """Implements a three layer GRU cell including an embedding layer
    and an output linear layer back to the size of the vocabulary"""

    def __init__(self, voc_size):
        super(MultiGRU, self).__init__()
        self.embedding = nn.Embedding(voc_size, 256)
        self.gru_1 = nn.GRUCell(256, 512)
        self.gru_2 = nn.GRUCell(512, 512)
        self.gru_3 = nn.GRUCell(512, 512)
        self.linear = nn.Linear(512, voc_size)

    def forward(self, x, h):
        device = x.device
        x = self.embedding(x)
        h_out = torch.zeros(h.size(), device=device)
        x = h_out[0] = self.gru_1(x, h[0])
        x = h_out[1] = self.gru_2(x, h[1])
        x = h_out[2] = self.gru_3(x, h[2])
        x = self.linear(x)
        return x, h_out

    def init_h(self, batch_size):
        return torch.zeros(3, batch_size, 512)


class RNN(nn.Module):
    """Implements the Prior and Agent RNN. Needs a Vocabulary instance in
    order to determine size of the vocabulary and index of the END token"""

    def __init__(self, voc):
        super(RNN, self).__init__()
        self.rnn = create_gru_model(len(voc))
        self.voc = voc

    @property
    def device(self):
        return next(self.parameters()).device

    def likelihood(self, target):
        """
        Retrieves the likelihood of a given sequence

        Args:
            target: (batch_size * sequence_lenght) A batch of sequences

        Outputs:
            log_probs : (batch_size) Log likelihood for each example*
            entropy: (batch_size) The entropies for the sequences. Not
                                  currently used.
        """
        device = self.device
        batch_size, seq_length = target.size()
        start_token = torch.zeros(batch_size, 1).long().to(device)
        start_token[:] = self.voc.vocab[self.voc.start_token]
        x = torch.cat((start_token, target[:, :-1]), 1)
        h = torch.zeros(3, batch_size, 512).to(device)

        log_probs = torch.zeros(batch_size).to(device)
        for step in range(seq_length):
            logits, h, _, _ = self.rnn(observation=x[:, step], recurrent_state=h)
            log_probs += torch.distributions.Categorical(logits=logits).log_prob(
                target[:, step]
            )

        return log_probs

    def forward(self, observation, max_length=140):
        """
        Sample a batch of sequences

        Args:
            observation : initial token for the sequences
            max_length:  Maximum length of the sequences

        Outputs:
        seqs: (batch_size, seq_length) The sampled sequences.
        log_probs : (batch_size) Log likelihood for each sequence.
        """

        device = self.device
        batch_size = observation.size()[0]
        h = torch.zeros(3, batch_size, 512).to(device)
        x = observation.long()

        sequences = torch.zeros(batch_size, max_length).long().to(device)
        log_probs = torch.zeros(batch_size).to(device)
        finished = torch.zeros(batch_size, dtype=torch.bool).to(device)

        for step in range(max_length):
            logits, h, x, logp = self.rnn(observation=x, recurrent_state=h)
            sequences[:, step][~finished] = x[~finished]
            log_probs += logp
            EOS_sampled = x == self.voc.vocab[self.voc.end_token]
            finished = torch.ge(finished + EOS_sampled, 1)
            if torch.prod(finished) == 1:
                break

        return sequences, log_probs


def create_gru_model(vocabulary):
    model = MultiGRU(vocabulary)
    td_model = TensorDictModule(
        model,
        in_keys=["observation", "recurrent_state"],
        out_keys=["logits", ("next", "recurrent_state")],
    )
    td_model = ProbabilisticActor(
        module=td_model,
        in_keys=["logits"],
        out_keys=["action"],
        distribution_class=torch.distributions.Categorical,
        return_log_prob=True,
        default_interaction_type=ExplorationType.RANDOM,
    )
    return td_model


def create_reinvent_model(vocabulary):
    model = RNN(vocabulary)
    td_model = TensorDictModule(
        model,
        in_keys=["observation"],
        out_keys=["action", "log_probs"],
    )
    return td_model
