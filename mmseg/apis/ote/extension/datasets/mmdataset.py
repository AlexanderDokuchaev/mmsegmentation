# Copyright (C) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

import json
import os
from typing import List, Optional

import cv2
import numpy as np
from ote_sdk.utils.segmentation_utils import mask_from_dataset_item
from ote_sdk.entities.annotation import Annotation, AnnotationSceneEntity, AnnotationSceneKind
from ote_sdk.entities.dataset_item import DatasetItemEntity
from ote_sdk.entities.datasets import DatasetEntity
from ote_sdk.entities.image import Image
from ote_sdk.entities.label import LabelEntity, Domain
from ote_sdk.entities.scored_label import ScoredLabel
from ote_sdk.entities.shapes.polygon import Point, Polygon
from ote_sdk.entities.subset import Subset

from mmseg.datasets.builder import DATASETS
from mmseg.datasets.custom import CustomDataset
from mmseg.datasets.pipelines import Compose


def get_annotation_mmseg_format(dataset_item: DatasetItemEntity, labels: List[LabelEntity]) -> dict:
    """
    Function to convert a OTE annotation to mmsegmentation format. This is used both
    in the OTEDataset class defined in this file as in the custom pipeline
    element 'LoadAnnotationFromOTEDataset'

    :param dataset_item: DatasetItem for which to get annotations
    :param labels: List of labels in the project
    :return dict: annotation information dict in mmseg format
    """

    gt_seg_map = mask_from_dataset_item(dataset_item, labels)
    gt_seg_map = gt_seg_map.squeeze(2).astype(np.uint8)

    ann_info = dict(gt_semantic_seg=gt_seg_map)

    return ann_info


@DATASETS.register_module()
class OTEDataset(CustomDataset):
    """
    Wrapper that allows using a OTE dataset to train mmsegmentation models. This wrapper is not based on the filesystem,
    but instead loads the items here directly from the OTE Dataset object.

    The wrapper overwrites some methods of the CustomDataset class: prepare_train_img, prepare_test_img and prepipeline
    Naming of certain attributes might seem a bit peculiar but this is due to the conventions set in CustomDataset. For
    instance, CustomDatasets expects the dataset items to be stored in the attribute data_infos, which is why it is
    named like that and not dataset_items.

    """

    class _DataInfoProxy:
        """
        This class is intended to be a wrapper to use it in CustomDataset-derived class as `self.data_infos`.
        Instead of using list `data_infos` as in CustomDataset, our implementation of dataset OTEDataset
        uses this proxy class with overriden __len__ and __getitem__; this proxy class
        forwards data access operations to ote_dataset and converts the dataset items to the view
        convenient for mmsegmentation.
        """
        def __init__(self, ote_dataset, labels=None):
            self.ote_dataset = ote_dataset
            self.labels = labels

        def __len__(self):
            return len(self.ote_dataset)

        def __getitem__(self, index):
            """
            Prepare a dict 'data_info' that is expected by the mmseg pipeline to handle images and annotations
            :return data_info: dictionary that contains the image and image metadata, as well as the labels of
            the objects in the image
            """

            dataset = self.ote_dataset
            item = dataset[index]

            data_info = dict(dataset_item=item,
                             width=item.width,
                             height=item.height,
                             index=index,
                             ann_info=dict(labels=self.labels))

            return data_info

    def __init__(self, ote_dataset: DatasetEntity, pipeline, classes=None, test_mode: bool = False):
        self.ote_dataset = ote_dataset
        self.test_mode = test_mode

        self.ignore_index = 255
        self.reduce_zero_label = False
        self.label_map = None

        dataset_labels = self.ote_dataset.get_labels(include_empty=False)
        self.project_labels = self.filter_labels(dataset_labels, classes)
        self.CLASSES, self.PALETTE = self.get_classes_and_palette(classes, None)

        # Instead of using list data_infos as in CustomDataset, this implementation of dataset
        # uses a proxy class with overriden __len__ and __getitem__; this proxy class
        # forwards data access operations to ote_dataset.
        # Note that list `data_infos` cannot be used here, since OTE dataset class does not have interface to
        # get only annotation of a data item, so we would load the whole data item (including image)
        # even if we need only checking aspect ratio of the image; due to it
        # this implementation of dataset does not uses such tricks as skipping images with wrong aspect ratios or
        # small image size, since otherwise reading the whole dataset during initialization will be required.
        self.data_infos = OTEDataset._DataInfoProxy(self.ote_dataset, self.project_labels)

        self.pipeline = Compose(pipeline)

    @staticmethod
    def filter_labels(all_labels, label_names):
        filtered_labels = []
        for label_name in label_names:
            matches = [label for label in all_labels if label.name == label_name]
            if len(matches) == 0:
                continue

            assert len(matches) == 1

            filtered_labels.append(matches[0])

        return filtered_labels

    def __len__(self):
        """Total number of samples of data."""

        return len(self.data_infos)

    def pre_pipeline(self, results):
        """Prepare results dict for pipeline."""

        results['seg_fields'] = []

    def prepare_train_img(self, idx: int) -> dict:
        """Get training data and annotations after pipeline.

        Args:
            idx (int): Index of data.

        Returns:
            dict: Training data and annotation after pipeline with new keys introduced by pipeline.
        """

        item = self.data_infos[idx]

        self.pre_pipeline(item)
        out = self.pipeline(item)

        return out

    def prepare_test_img(self, idx: int) -> dict:
        """Get testing data after pipeline.

        Args:
            idx (int): Index of data.

        Returns:
            dict: Testing data after pipeline with new keys introduced by pipeline.
        """

        item = self.data_infos[idx]

        self.pre_pipeline(item)
        out = self.pipeline(item)

        return out

    def get_ann_info(self, idx):
        """
        This method is used for evaluation of predictions. The CustomDataset class implements a method
        CustomDataset.evaluate, which uses the class method get_ann_info to retrieve annotations.

        :param idx: index of the dataset item for which to get the annotations
        :return ann_info: dict that contains the coordinates of the bboxes and their corresponding labels
        """

        dataset_item = self.ote_dataset[idx]
        ann_info = get_annotation_mmseg_format(dataset_item, self.project_labels)

        return ann_info

    def get_gt_seg_maps(self, efficient_test=False):
        """Get ground truth segmentation maps for evaluation."""

        gt_seg_maps = []
        for item_id in range(len(self)):
            ann_info = self.get_ann_info(item_id)
            gt_seg_maps.append(ann_info['gt_semantic_seg'])

        return gt_seg_maps


def get_classes_from_annotation(annot_path):
    with open(annot_path) as input_stream:
        content = json.load(input_stream)
        labels_map = content['labels_map']

        categories = [(v['name'], v['id']) for v in sorted(labels_map, key=lambda tup: int(tup['id']))]

    return categories


def abs_path_if_valid(value):
    if value:
        return os.path.abspath(value)
    else:
        return None


def create_annotation_from_hard_seg_map(hard_seg_map: np.ndarray, labels: List[LabelEntity]):
    height, width = hard_seg_map.shape[:2]
    unique_labels = np.unique(hard_seg_map)

    annotations: List[Annotation] = []
    for label_id in unique_labels:
        matches = [label for label in labels if label.id == label_id]
        if len(matches) == 0:
            continue

        assert len(matches) == 1
        label = matches[0]

        label_mask = (hard_seg_map == label_id)
        label_index_map = label_mask.astype(np.uint8)

        contours, hierarchies = cv2.findContours(
            label_index_map, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )

        if hierarchies is None:
            continue

        for contour, hierarchy in zip(contours, hierarchies[0]):
            if hierarchy[3] != -1:
                continue

            contour = list(contour)
            if len(contour) <= 2:
                continue

            points = [
                Point(x=point[0][0] / width, y=point[0][1] / height)
                for point in contour
            ]

            annotations.append(Annotation(
                    Polygon(points=points),
                    labels=[ScoredLabel(label)],
                    id=label_id,
            ))

    return annotations


def load_labels_from_annotation(ann_dir):
    if ann_dir is None:
        return []

    labels_map_path = os.path.join(ann_dir, 'meta.json')
    labels = get_classes_from_annotation(labels_map_path)

    return labels


def add_labels(cur_labels, new_labels):
    for label_name, label_id in new_labels:
        matching_labels = [label for label in cur_labels if label.name == label_name]
        if len(matching_labels) > 1:
            raise ValueError("Found multiple matching labels")
        elif len(matching_labels) == 0:
            label_id = label_id if label_id is not None else len(cur_labels)
            label = LabelEntity(name=label_name,
                                domain=Domain.SEGMENTATION,
                                id=label_id)
            cur_labels.append(label)


def check_labels(cur_labels, new_labels):
    cur_names = {label.name for label in cur_labels}
    new_names = {label[0] for label in new_labels}
    if cur_names != new_names:
        raise ValueError("Class names don't match from file to file")


def get_extended_label_names(labels):
    target_labels = [v.name for v in sorted(labels, key=lambda x: x.id)]
    all_labels = ['background'] + target_labels
    return all_labels


def load_dataset_items(ann_file_path: str,
                       data_root_dir: str,
                       subset: Subset = Subset.NONE,
                       labels_list: Optional[List[LabelEntity]] = None):
    ann_dir = abs_path_if_valid(ann_file_path)
    img_dir = abs_path_if_valid(data_root_dir)

    annot_labels = load_labels_from_annotation(ann_dir)

    if labels_list is None:
        labels_list = []
    if len(labels_list) == 0:
        add_labels(labels_list, annot_labels)
    else:
        check_labels(labels_list, annot_labels)

    test_mode = subset in {Subset.VALIDATION, Subset.TESTING}
    pipeline = [dict(type='LoadImageFromFile'),
                dict(type='Normalize', mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0], to_rgb=True),
                dict(type='LoadAnnotations')]
    dataset = CustomDataset(img_dir=img_dir,
                            ann_dir=ann_dir,
                            pipeline=pipeline,
                            classes=get_extended_label_names(labels_list),
                            test_mode=test_mode)
    dataset.test_mode = False

    dataset_items = []
    for item in dataset:
        annotations = create_annotation_from_hard_seg_map(hard_seg_map=item['gt_semantic_seg'],
                                                          labels=labels_list)
        image = Image(data=item['img'])
        annotation_scene = AnnotationSceneEntity(kind=AnnotationSceneKind.ANNOTATION,
                                                 annotations=annotations)
        dataset_items.append(DatasetItemEntity(media=image,
                                               annotation_scene=annotation_scene,
                                               subset=subset))

    return dataset_items
