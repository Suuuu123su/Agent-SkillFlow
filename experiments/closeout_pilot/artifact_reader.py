"""Read preserved native workspaces from a byte-exact archive without extracting."""
from pathlib import PurePosixPath
import tarfile

from .paths import confined


class EvidenceReader:
    def __init__(self, root):
        self.root = root
        self.members = {}
        for archive_name in ('WORKSPACES.tar.gz', 'WORKSPACES_EXTRA.tar.gz'):
            archive = root/archive_name
            if not archive.exists():
                continue
            with tarfile.open(archive, 'r:gz') as tar:
                for item in tar.getmembers():
                    if not item.isfile():
                        raise ValueError('Non-file archive member')
                    confined(root, item.name)
                    if item.name in self.members:
                        raise ValueError('Duplicate archive member')
                    self.members[item.name] = tar.extractfile(item).read()

    def path(self, relative):
        confined(self.root, relative)
        return EvidencePath(self, PurePosixPath(relative))


class EvidencePath:
    def __init__(self, reader, relative):
        self.reader, self.relative = reader, relative

    def __truediv__(self, child):
        return self.reader.path((self.relative/child).as_posix())

    def read_bytes(self):
        name = self.relative.as_posix()
        if name in self.reader.members:
            return self.reader.members[name]
        return confined(self.reader.root, name).read_bytes()

    def read_text(self, encoding='utf-8', errors='strict'):
        return self.read_bytes().decode(encoding, errors).replace('\r\n', '\n').replace('\r', '\n')
