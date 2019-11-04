#!/usr/bin/env python
# coding: utf-8


from __future__ import print_function

import torch
import torch.nn as nn
import torch.optim as optim

import numpy as np
import torchvision
from torchvision import datasets, models, transforms

import copy
import os
import shutil


def init_reg_params(model, use_gpu, freeze_layers = []):
	"""
	Input:
	1) model: A reference to the model that is being trained
	2) freeze_layers: A layer which 

	Output:
	1) reg_params: A dictionary containing importance weights (omega), init_val (keep a reference 
	to the initial values of the parameters) for all trainable parameters


	Function:
	"""
	device = torch.device("cuda:0" if use_gpu else "cpu")

	reg_params = {}

	for name, param in model.tmodel.named_parameters():
		if not name in freeze_layers:
			
			print ("Initializing omega values for layer", name)
			omega = torch.zeros(param.size())
			omega = omega.to(device)

			init_val = param.data.clone()
			param_dict = {}

			#for first task, omega is initialized to zero
			param_dict['omega'] = omega
			param_dict['init_val'] = init_val

			#the key for this dictionary is the name of the layer
			reg_params[param] = param_dict

	model.reg_params = reg_params

	return model


def init_reg_params_across_tasks(model, use_gpu, freeze_layers = []):
	"""
	Input:
	1) model: A reference to the model that is being trained

	Output:
	1) reg_params: A dictionary containing importance weights (omega), init_val (keep a reference 
	to the initial values of the parameters) for all trainable parameters


	Function:
	"""

	#Get the reg_params for the model 
	
	device = torch.device("cuda:0" if use_gpu else "cpu")

	reg_params = model.reg_params

	for name, param in model.tmodel.named_parameters():
		
		if not name in freeze_layers:

			param_dict = reg_params[param]
			print ("Initializing the omega values for layer for the new task", name)
			
			#Store the previous values of omega
			prev_omega = param_dict['omega']
			
			#Initialize a new omega
			new_omega = torch.zeros(param.size())
			new_omega = new_omega.to(device)

			init_val = param.data.clone()
			init_val = init_val.to(device)

			param_dict['prev_omega'] = prev_omega
			param_dict['omega'] = new_omega

			#store the initial values of the parameters
			param_dict['init_val'] = init_val

			#the key for this dictionary is the name of the layer
			reg_params[param] =  param_dict

	model.reg_params = reg_params

	return model


def consolidate_reg_params(model, use_gpu):
	"""
	Input:
	1) model: A reference to the model that is being trained

	Output:
	1) reg_params: A dictionary containing importance weights (omega), init_val (keep a reference 
	to the initial values of the parameters) for all trainable parameters


	Function:
	"""

	#Get the reg_params for the model 
	reg_params = model.reg_params

	for name, param in model.tmodel.named_parameters():
		
		param_dict = reg_params[name]
		print ("Consolidating the omega values for layer", name)
		
		#Store the previous values of omega
		prev_omega = param_dict['prev_omega']
		new_omega = param_dict['omega']

		new_omega = torch.add(prev_omega, new_omega)
		del param_dict['prev_omega']
		
		param_dict['omega'] = new_omega

		#the key for this dictionary is the name of the layer
		reg_params[param] = param_dict

	model.reg_params = reg_params

	return model


def compute_omega_grads_norm(model, dataloader, optimizer):
	"""
	global version for computing the l2 norm of the function (neural network's) outputs
	This function also fills up the parameter values
	"""
	
	#Alexnet object
	model.tmodel.eval()

	index = 0
	for data in dataloader['train']:
		
		#get the inputs and labels
		inputs, labels = data

		if(use_gpu):
			device = torch.device("cuda:0" if use_gpu else "cpu")
			inputs, labels = inputs.to(device), labels.to(device)

		#Zero the parameter gradients
		optimizer.zero_grad()

		#get the function outputs
		outputs = model.tmodel(inputs)
		del inputs

		#compute the sqaured l2 norm of the function outputs
		l2_norm = torch.norm(outputs, 2, dim = 1)
		del outputs

		squared_l2_norm = l2_norm**2
		del squared_l2_norm
		
		sum_norm = torch.sum(squared_l2_norm)
		
		#compute gradients for these parameters
		sum_norm.backward()

		#optimizer.step computes the omega values for the new batches of data
		optimizer.step(model.reg_params, index, labels.size(0))
		del labels
		
		index = index + 1

	return model


#need a different function for grads vector
def compute_omega_grads_vector(model, dataloader, optimizer):
	"""
	global version for computing
	"""

	#Alexnet object
	model.tmodel.train(False)
	model.tmodel.eval(True)

	index = 0

	for dataloader in dset_loaders:
		for data in dataloader:
			
			#get the inputs and labels
			inputs, labels = data

			if(use_gpu):
				device = torch.device("cuda:0")
				inputs, labels = inputs.to(device), labels.to(device)

			#Zero the parameter gradients
			optimizer.zero_grad()

			#get the function outputs
			outputs = model.tmodel(inputs)

			for unit_no in range(0, outputs.size(1)):
				ith_node = outputs[:, unit_no]
				targets = torch.sum(ith_node)

				#final node in the layer
				if(node_no == outputs.size(1)-1):
					targets.backward()
				else:
					#This retains the computational graph for further computations 
					targets.backward(retain_graph = True)

				optimizer.step(model.reg_params, False, index, labels.size(0))
				
				#necessary to compute the correct gradients for each batch of data
				optimizer.zero_grad()

			
			optimizer.step(model.reg_params, True, index, labels.size(0))
			index = index + 1

	return model


#sanity check for the model to check if the omega values are getting updated
def sanity_model(model):
	
	for name, param in model.tmodel.named_parameters():
		
		print (name)
		
		if param in model.reg_params:
			param_dict = model.reg_params[param]
			omega = param_dict['omega']

			print ("Max omega is", omega.max())
			print ("Min omega is", omega.min())
			print ("Mean value of omega is", omega.min())



#function to freeze selected layers
def create_freeze_layers(model, no_of_layers = 2):
	"""
	Inputs
	1) model: A reference to the model
	2) no_of_layers: The number of convolutional layers that you want to freeze in the convolutional base of 
		Alexnet model. Default value is 2 

	Outputs
	1) freeze_layers: Creates a list of layers that will not be involved in the training process

	Function: This function creates the freeze_layers list which is then passed to the `compute_omega_grads_norm`
	function which then checks the list to see if the omegas need to be calculated for the parameters of these layers  
	
	"""
	
	#The require_grad attribute for the parameters of the classifier layer is set to True by default 
	for param in model.tmodel.classifier.parameters():
		param.requires_grad = True

	for param in model.tmodel.features.parameters():
		param.requires_grad = False

	#return an empty list if you want to train the entire model
	if (no_of_layers == 0):
		return []

	temp_list = []
	freeze_layers = []

	#get the keys for the conv layers in the model
	for key in model.tmodel.features._modules:
		if (type(model.tmodel.features._modules[key]) == torch.nn.modules.conv.Conv2d):
			temp_list.append(key)
	
	#set the requires_grad attribute to True for the layers you want to be trainable
	for num in range(1, no_of_layers + 1):
		#pick the layers from the end
		temp_key = temp_list[-1 * num]
		
		for param in model.tmodel.features[int(temp_key)].parameters():
			param.requires_grad = True

		name_1 = 'features.' + temp_key + 'weight'
		name_2 = 'features.' + temp_key + 'bias'

		freeze_layers.append(name_1)
		freeze_layers.append(name_2)


	return [model, freeze_layers]


	





