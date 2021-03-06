# Copyright 2020 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import tempfile
import unittest
from multiprocessing import Lock

import nibabel as nib
import numpy as np

from monai.data import DataLoader, IterableDataset
from monai.transforms import Compose, LoadImaged, SimulateDelayd

lock = Lock()


class _Stream:
    def __init__(self, data, dbpath):
        # simulate a database at the website
        self.dbpath = dbpath
        self.reset()
        self.data = data

    def __iter__(self):
        return self

    def __next__(self):
        data = None
        # support multi-process access to the database
        lock.acquire()
        with open(self.dbpath) as f:
            count = json.load(f)["count"]
        if count > 0:
            data = self.data[count - 1]
            with open(self.dbpath, "w") as f:
                json.dump({"count": count - 1}, f)
        lock.release()

        if count == 0:
            raise StopIteration
        return data

    def reset(self):
        with open(self.dbpath, "w") as f:
            json.dump({"count": 6}, f)


class TestIterableDataset(unittest.TestCase):
    def test_shape(self):
        expected_shape = (128, 128, 128)
        test_image = nib.Nifti1Image(np.random.randint(0, 2, size=[128, 128, 128]), np.eye(4))
        test_data = list()
        with tempfile.TemporaryDirectory() as tempdir:
            for i in range(6):
                nib.save(test_image, os.path.join(tempdir, f"test_image{str(i)}.nii.gz"))
                test_data.append({"image": os.path.join(tempdir, f"test_image{str(i)}.nii.gz")})

            test_transform = Compose(
                [
                    LoadImaged(keys="image"),
                    SimulateDelayd(keys="image", delay_time=1e-7),
                ]
            )

            test_stream = _Stream(data=test_data, dbpath=os.path.join(tempdir, "countDB"))

            dataset = IterableDataset(data=test_stream, transform=test_transform)
            for d in dataset:
                self.assertTupleEqual(d["image"].shape, expected_shape)

            test_stream.reset()
            dataloader = DataLoader(dataset=dataset, batch_size=3, num_workers=2)
            for d in dataloader:
                self.assertTupleEqual(d["image"].shape[1:], expected_shape)


if __name__ == "__main__":
    unittest.main()
