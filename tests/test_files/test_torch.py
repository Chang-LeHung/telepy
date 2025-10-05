import argparse
import sys
import urllib.request
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

MNIST_URL = "https://storage.googleapis.com/tensorflow/tf-keras-datasets/mnist.npz"
DEFAULT_CACHE = Path.home() / ".mnist" / "mnist.npz"


def ensure_dataset(path: Path) -> Path:
    """Download MNIST dataset if it does not exist at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    print(f"Downloading MNIST dataset to {path} ...")
    try:
        urllib.request.urlretrieve(MNIST_URL, path)
    except Exception as exc:  # pragma: no cover - network errors are environment specific
        raise RuntimeError(
            "Unable to download MNIST dataset. Set --data-path to an existing mnist.npz file."  # noqa: E501
        ) from exc
    return path


def load_mnist(
    data_path: str | None = None,
) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
    """Load MNIST data, downloading if necessary."""
    if data_path is not None:
        candidate = Path(data_path)
        if candidate.is_dir():
            candidate = candidate / "mnist.npz"
        dataset_path = candidate
    else:
        dataset_path = DEFAULT_CACHE

    dataset_path = ensure_dataset(dataset_path)

    with np.load(dataset_path) as data:
        x_train = data["x_train"].astype(np.float32) / 255.0
        y_train = data["y_train"].astype(np.int64)
        x_test = data["x_test"].astype(np.float32) / 255.0
        y_test = data["y_test"].astype(np.int64)

    x_train = x_train.reshape(len(x_train), -1)
    x_test = x_test.reshape(len(x_test), -1)
    return (x_train, y_train), (x_test, y_test)


class MNISTClassifier(nn.Module):
    def __init__(
        self,
        input_dim: int = 28 * 28,
        hidden_dim: int = 128,
        num_classes: int = 10,
        learning_rate: float = 0.1,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        if seed is not None:
            torch.manual_seed(seed)
        self.learning_rate = learning_rate
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, num_classes),
        )
        self.criterion = nn.CrossEntropyLoss()

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.net(inputs)

    @staticmethod
    def _move_batch(
        batch: tuple[torch.Tensor, torch.Tensor], device: torch.device
    ) -> tuple[torch.Tensor, torch.Tensor]:
        features, labels = batch
        return features.to(device), labels.to(device)

    def fit(
        self,
        train_loader: DataLoader,
        *,
        epochs: int = 5,
        device: torch.device,
        val_loader: DataLoader | None = None,
    ) -> None:
        optimizer = torch.optim.SGD(self.parameters(), lr=self.learning_rate)

        for epoch in range(1, epochs + 1):
            self.train()
            epoch_loss = 0.0
            total_samples = 0

            for batch in train_loader:
                batch_X, batch_y = self._move_batch(batch, device)
                optimizer.zero_grad()
                logits = self(batch_X)
                loss = self.criterion(logits, batch_y)
                loss.backward()
                optimizer.step()

                batch_size = batch_X.size(0)
                epoch_loss += loss.item() * batch_size
                total_samples += batch_size

            average_loss = epoch_loss / max(total_samples, 1)
            message = f"Epoch {epoch}: loss={average_loss:.4f}"
            if val_loader is not None:
                val_acc = self.evaluate(val_loader, device=device)
                message += f", val_acc={val_acc:.4f}"
            print(message)

    def evaluate(self, data_loader: DataLoader, *, device: torch.device) -> float:
        was_training = self.training
        self.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for batch in data_loader:
                batch_X, batch_y = self._move_batch(batch, device)
                logits = self(batch_X)
                predictions = torch.argmax(logits, dim=1)
                correct += (predictions == batch_y).sum().item()
                total += batch_X.size(0)

        if was_training:
            self.train()

        return float(correct / total) if total else 0.0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train a simple MNIST classifier implemented with PyTorch."
    )
    parser.add_argument(
        "--epochs", type=int, default=5, help="Number of training epochs."
    )
    parser.add_argument("--batch-size", type=int, default=128, help="Mini-batch size.")
    parser.add_argument("--hidden-dim", type=int, default=128, help="Hidden layer width.")
    parser.add_argument(
        "--learning-rate", type=float, default=0.1, help="Learning rate for SGD."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to mnist.npz (defaults to ~/.mnist/mnist.npz).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    args = parser.parse_args(argv)

    (x_train, y_train), (x_test, y_test) = load_mnist(args.data_path)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    x_train_tensor = torch.from_numpy(x_train)
    y_train_tensor = torch.from_numpy(y_train)
    x_test_tensor = torch.from_numpy(x_test)
    y_test_tensor = torch.from_numpy(y_test)

    train_dataset = TensorDataset(x_train_tensor, y_train_tensor)
    test_dataset = TensorDataset(x_test_tensor, y_test_tensor)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    model = MNISTClassifier(
        hidden_dim=args.hidden_dim, learning_rate=args.learning_rate, seed=args.seed
    )
    model.to(device)
    try:
        model.fit(train_loader, epochs=args.epochs, device=device, val_loader=test_loader)
    except KeyboardInterrupt:  # pragma: no cover - manual interruption
        print("Training interrupted by user.")

    test_acc = model.evaluate(test_loader, device=device)
    print(f"Test accuracy: {test_acc:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
