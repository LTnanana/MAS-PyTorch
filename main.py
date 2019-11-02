#!/usr/bin/env python
# coding: utf-8

import torch
torch.backends.cudnn.benchmark=True

import torch.nn as nn
from torch.autograd import Variable
import torch.optim as optim
import torch.nn.functional as F

import torchvision.datasets as datasets
import torchvision.models as models
import torchvision.transforms as transforms

import argparse 
import numpy as np
from random import shuffle

import copy

sys.path.append('utils')
from model_utils import *
from mas_utils import *

from optimizer_lib import *
from model_train import *

parser = argparse.ArgumentParser(description='Test file')
parser.add_argument('--use_gpu', default=False, type=bool, help = 'Set the flag if you wish to use the GPU')
parser.add_argument('--batch_size', default=32, type=int, help = 'The batch size you want to use')
parser.add_argument('--num_freeze_layers', default=2, type=int, help = 'Number of layers you want to frozen in the feature extractor of the model')

args = parser.parse_args()
use_gpu = args.use_gpu
batch_size = args.batch_size
no_of_layers = args.freeze_layers

dloaders_train = []
dloaders_test = []

dsets_train = []
dsets_test = []

num_classes = []

data_path = os.path.join(os.getcwd(), "Data")

data_transforms = {
	'train': transforms.Compose([
		transforms.RandomResizedCrop(224),
		transforms.RandomHorizontalFlip(),
		transforms.ToTensor(),
		transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
	]),

	'test': transforms.Compose([
		transforms.Resize(256),
		transforms.CenterCrop(224),
		transforms.ToTensor(),
		transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
	])
}



data_dir = os.path.join(os.getcwd(), "Data")


#create the dataloaders for all the tasks
for tdir in os.listdir(data_dir):

	#create the image folders objects
	tr_image_folder = datasets.ImageFolder(os.path.join(data_dir, tdir), transform = data_transforms['train'])
	te_image_folder = datasets.ImageFolder(os.path.join(data_dir, tdir), transform = data_transforms['test'])

	#get the dataloaders
	tr_dset_loaders = torch.utils.data.DataLoader(tr_image_folder, batch_size=batch_size, shuffle=True, num_workers=4)
	te_dset_loaders = torch.utils.data.Dataloader(te_image_folder, batch_size=batch_size, shuffle=True, num_workers=4)

	#get the sizes
	temp1 = len(tr_image_folder) 
	temp2 = len(te_image_folder)


	#append the dataloaders of these tasks
	dloaders_train.append(tr_dset_loaders)
	dloaders_test.append(te_dset_loaders)

	#get the classes (THIS MIGHT NEED TO BE CORRECTED)
	num_classes.append(len(tr_image_folder.classes))


	#get the sizes array
	dsets_train.append(temp1)
	dsets_test.append(temp2)



no_of_tasks = len(dloaders_train)

model = shared_model(models.alexnet(pretrained = True))

#train the model on the given number of tasks
for task in range(1, no_of_tasks+1):
	print ("Training the model on task {}".format(task))

	dataloader = dloaders_train[task-1]
	dset_size = dsets_train[task-1]
	no_of_classes = num_classes[task-1]

	mas_train(model, task, no_of_layers, no_of_classes, dataloader, dset_size, use_gpu)



print ("The training process on the {} tasks is completed".format(no_of_tasks))





