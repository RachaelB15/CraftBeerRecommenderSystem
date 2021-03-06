# -*- coding: utf-8 -*-
"""MachineLearningFinal_PyTorch_RachaelBurris.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/gist/RachaelB15/5e726f61b173334835907a17c5a80a7f/machinelearningfinal_pytorch_rachaelburris.ipynb

# Recommender System Exploration: PyTorch

Team Members:Rachael Burris, Emily Luskind, Melanie Tran

Pytorch Model Development:Rachael

### Install and Load packages
"""

#!pip install pytorch-lightning

# Commented out IPython magic to ensure Python compatibility.
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# %matplotlib inline
import seaborn as sns

## PyTorch
import torch
from torch.utils.data import Dataset
import torch.nn as nn
from torch.utils.data import DataLoader
import pytorch_lightning as pl
import torchmetrics
from pytorch_lightning.callbacks import ModelCheckpoint
import pytorch_lightning

## additional needs ##
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from keras.callbacks import TensorBoard
from keras.models import Sequential, load_model
from keras.layers import LSTM, Dense, Dropout
from keras.layers.embeddings import Embedding
from keras.preprocessing import sequence
from keras.preprocessing.text import Tokenizer
import collections
from collections import OrderedDict

## plotting
from sklearn.manifold import TSNE

"""### Mount Drive and Load Data"""

df = pd.read_csv('https://query.data.world/s/clrh2qyreg5umg327kiirhfh3qws2e')
## or, to access the file locally
#path='your/path/here'
#df = pd.read_csv(path+"beer_reviews.csv")
df.head()

##create beer lookup table
beer_lookup_table=df[['beer_beerid','beer_name']]
beer_lookup_table=beer_lookup_table.drop_duplicates()   ##for returning beer names based on ID later

df.head()

"""# EDA"""

##view the beer styles with the most reviews
top_styles=df.beer_style.value_counts()[:7]
top_styles

##grab rating columns
nums=df[['review_overall','review_aroma','review_appearance','review_palate','review_taste','beer_style']]

##view the most reviewed beer ratings only
top_nums=nums[nums['beer_style'].isin(top_styles.index)]

##melt all review columns into a single column
top_nums=top_nums.melt(value_vars=['review_overall','review_aroma','review_appearance','review_palate','review_taste'], id_vars=['beer_style'])
top_nums.columns=(['Beer Style','Review Type','Rating'])

##plot most review beer values in seaborn
plt.figure(figsize=(20,8))
sns.violinplot(data=top_nums,y='Rating',x='Beer Style',hue='Review Type',palette='bright')

#display statistics on most reviewed beers
top_nums.groupby('Beer Style').describe()

print('Unique Styles of beer:  ',len(df.beer_style.unique()))
print('Unique Names of beer:   ',len(df.beer_name.unique()))
print('Unique Users:           ',len(df.review_profilename.unique()))
print('Total Reviews:          ',len(df))

"""# Model Prep"""

df=df[['beer_beerid','review_overall','review_profilename','review_time']]  # keep only neccessary columns

names = df['review_profilename']    # create user ids
codes, uniques = pd.factorize(names)
df['user_id'] = codes

#create train and test using leave one out method
df['rank_latest'] = df.groupby(['user_id'])['review_time'].rank(method='first', ascending=False)

train = df[df['rank_latest'] != 1]
test = df[df['rank_latest'] == 1]

# drop columns that we no longer need
train = train[['user_id', 'beer_beerid', 'review_overall']]
test = test[['user_id', 'beer_beerid', 'review_overall']]

train.loc[:, 'review_overall'] = 1

x=train[train.user_id < 0].index
y=test[test.user_id < 0].index
train=train.drop(x,axis=0 )
test=test.drop(y,axis=0 )

# Get a list of all movie IDs
all_beerIds = df['beer_beerid'].unique()

# Placeholders that will hold the training data
users, items, labels = [], [], []

# This is the set of items that each user has interaction with
user_item_set = set(zip(train['user_id'], train['beer_beerid']))

# 4:1 ratio of negative to positive samples
num_negatives = 4

for (u, i) in user_item_set:
    users.append(u)
    items.append(i)
    labels.append(1) # items that the user has interacted with are positive
    for _ in range(num_negatives):
        # randomly select an item
        negative_item = np.random.choice(all_beerIds) 
        # check that the user has not interacted with this item
        while (u, negative_item) in user_item_set:
            negative_item = np.random.choice(all_beerIds)
        users.append(u)
        items.append(negative_item)
        labels.append(0) # items not interacted with are negative

"""# PyTorch Lightning

 from TDS https://towardsdatascience.com/deep-learning-based-recommender-systems-3d120201db7e

## Create Functions to execute Model
"""

#lets create training and test sets
class TrainDataset(Dataset):
    """
    Args:
        df (pd.DataFrame): Dataframe containing the beer df
        all_beerIds (list): List containing all beerIds
    
    """
    def __init__(self, df, all_beerIds):
        self.users, self.items, self.labels = self.get_dataset(df, all_beerIds)

    def __len__(self):
        return len(self.users)
  
    def __getitem__(self, idx):
        return self.users[idx], self.items[idx], self.labels[idx]

    def get_dataset(self, df, all_beerIds):
        users, items, labels = [], [], []
        user_item_set = set(zip(df['user_id'], df['beer_beerid']))

        num_negatives = 4
        for u, i in user_item_set:
            users.append(u)
            items.append(i)
            labels.append(1)
            for _ in range(num_negatives):
                negative_item = np.random.choice(all_beerIds)
                while (u, negative_item) in user_item_set:
                    negative_item = np.random.choice(all_beerIds)
                users.append(u)
                items.append(negative_item)
                labels.append(0)

        return torch.tensor(users), torch.tensor(items), torch.tensor(labels)

class ValDataset(Dataset):
    """
    Args:
        df (pd.DataFrame): Dataframe containing the beer df
        all_beerIds (list): List containing all beerIds
    
    """

    def __init__(self, df, all_beerIds):
        self.users, self.items, self.labels = self.get_dataset(df, all_beerIds)

    def __len__(self):
        return len(self.users)
  
    def __getitem__(self, idx):
        return self.users[idx], self.items[idx], self.labels[idx]

    def get_dataset(self, df, all_beerIds):
        users, items, labels = [], [], []
        user_item_set = set(zip(df['user_id'], df['beer_beerid']))

        num_negatives = 4
        for u, i in user_item_set:
            users.append(u)
            items.append(i)
            labels.append(1)
            for _ in range(num_negatives):
                negative_item = np.random.choice(all_beerIds)
                while (u, negative_item) in user_item_set:
                    negative_item = np.random.choice(all_beerIds)
                users.append(u)
                items.append(negative_item)
                labels.append(0)

        return torch.tensor(users), torch.tensor(items), torch.tensor(labels)

#set up log file
from pytorch_lightning import loggers as pl_loggers
tb_logger = pl_loggers.TensorBoardLogger("logs/")

#create model class
class NCF(pl.LightningModule):
    """ Neural Collaborative Filtering (NCF)
    
        Args:
            num_users (int): Number of unique users
            num_items (int): Number of unique items
            df (pd.DataFrame): Dataframe containing the beer ratings for training
            all_beerIds (list): List containing all beerIds (train + test)
    """
    
    def __init__(self, num_users, num_items, train, test, all_beerIds):
        super().__init__()
        self.user_embedding = nn.Embedding(num_embeddings=num_users, embedding_dim=8)
        self.item_embedding = nn.Embedding(num_embeddings=num_items, embedding_dim=8)
        self.fc1 = nn.Linear(in_features=16, out_features=64)
        self.fc2 = nn.Linear(in_features=64, out_features=32)
        self.output = nn.Linear(in_features=32, out_features=1)
        self.ratings = train
        self.test = test
        self.all_beerIds = all_beerIds
        self.train_acc = torchmetrics.MeanSquaredError(squared=False) #added
        self.valid_acc = torchmetrics.MeanSquaredError(squared=False) #added

        
    def forward(self, user_input, item_input):
        
        # Pass through embedding layers
        user_embedded = self.user_embedding(user_input)
        item_embedded = self.item_embedding(item_input)

        # Concat the two embedding layers
        vector = torch.cat([user_embedded, item_embedded], dim=1)

        # Pass through dense layer
        vector = nn.ReLU()(self.fc1(vector))
        vector = nn.ReLU()(self.fc2(vector))

        # Output layer
        pred = nn.Sigmoid()(self.output(vector))

        return pred
    
    def training_step(self, batch, batch_idx):
        user_input, item_input, labels = batch
        predicted_labels = self(user_input, item_input)
        loss = nn.MSELoss()(predicted_labels, labels.view(-1, 1).float())
        self.log("train_loss", loss, prog_bar=True, sync_dist=True, logger=True)                                     #
        self.log('train_acc',self.train_acc(predicted_labels,labels.view(-1, 1).float()))                 #
        return loss
      
    def training_epoch_end(self,outs):
      self.log('train_acc_epoc',self.train_acc.compute(),prog_bar=True, logger=True)

    def validation_step(self, batch, batch_idx):
        user_input, item_input, labels = batch
        predicted_labels = self(user_input, item_input) 
        val_rmse=self.valid_acc(predicted_labels,labels.view(-1, 1).float())
        self.log('valid_acc',self.valid_acc(predicted_labels,labels.view(-1, 1).float()), prog_bar=True, logger=True)

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters())

    def train_dataloader(self):
        return DataLoader(TrainDataset(self.ratings, self.all_beerIds),
                          batch_size=5000, num_workers=4)
    def val_dataloader(self):
        return DataLoader(ValDataset(self.test, self.all_beerIds),
                          batch_size=5000, num_workers=4)

#we'll use this code to evaluate our model
def PyEvaluator(model,train,test):
  # User-item pairs for testing
  test_user_item_set = set(zip(test['user_id'], test['beer_beerid']))

    # Dict of all items that are interacted with by each user
  user_interacted_items = df.groupby('user_id')['beer_beerid'].apply(list).to_dict()

  hits = []
  results= pd.DataFrame(test_user_item_set)
  results.columns=['User ID','Beer ID']
  results['Top10']=""

  for (u,i) in test_user_item_set:
      interacted_items = user_interacted_items[u]
      not_interacted_items = set(all_beerIds) - set(interacted_items)
      selected_not_interacted = list(np.random.choice(list(not_interacted_items), 99))
      test_items = selected_not_interacted + [i]
      
      predicted_labels = np.squeeze(model(torch.tensor([u]*100), 
                                          torch.tensor(test_items)).detach().numpy())
      
      top10_items = [test_items[i] for i in np.argsort(predicted_labels)[::-1][0:10].tolist()]

      results['Top10'][u]=top10_items

      if i in top10_items:
          hits.append(1)
      else:
          hits.append(0)

  print("The Hit Ratio @ 10 is {:.2f}".format(np.average(hits)))
  return hits, results

#and finally, this code to use our recommender system
def GetRecs(user_id):
  x = results[results['User ID'].isin([user_id])].Top10
  recs = beer_lookup_table[beer_lookup_table['beer_beerid'].isin(x.values[0])]
  user_reviews=df[df['user_id'].isin([user_id])]
  hits=user_reviews[user_reviews['beer_beerid'].isin(x.values[0])]
  return recs,hits

"""## Training


"""

callbacks= [pl.callbacks.ModelCheckpoint(path+'M5best', save_top_k=1)]

num_users = df['user_id'].max()+1
num_items = df['beer_beerid'].max()+1
all_beerIds = df['beer_beerid'].unique()

model = NCF(num_users, num_items, train, test, all_beerIds)

trainer = pl.Trainer(max_epochs=5, gpus=1, reload_dataloaders_every_n_epochs=True, 
                     progress_bar_refresh_rate=50, logger=tb_logger, callbacks=callbacks)

M1=trainer.fit(model)

##access the training log
trainer.logged_metrics

"""## Store and Load

"""

PATH = path+"PyTorchModelv5.pt"

# To Save
torch.save(model.state_dict(), PATH)

# To Load
#PATH = path+"PyTorchModelv5.pt"
#device = torch.device('cpu')
#model = NCF(num_users, num_items, df,test,all_beerIds)
#model.load_state_dict(torch.load(PATH, map_location=device))

"""## Evaluate"""

PyEvaluator(model,train,test)

recs,hits = GetRecs(3)
hits

recs

"""# Keras

from https://towardsdatascience.com/recommender-systems-from-learned-embeddings-f1d12288f278

## Functions
"""

def EmbeddingRec(EMBEDDING_SIZE, NUM_MOVIES, NUM_USERS, ROW_COUNT):
    movie_input = keras.Input(shape=(1,), name='movie_id')

    movie_emb = layers.Embedding(output_dim=EMBEDDING_SIZE, input_dim=NUM_MOVIES, input_length=ROW_COUNT, name='movie_emb')(movie_input)
    movie_vec = layers.Flatten(name='FlattenMovie')(movie_emb)

    movie_model = keras.Model(inputs=movie_input, outputs=movie_vec)
    
    user_input = keras.Input(shape=(1,), name='user_id')

    user_emb = layers.Embedding(output_dim=EMBEDDING_SIZE, input_dim=NUM_USERS, input_length=ROW_COUNT, name='user_emb')(user_input)
    user_vec = layers.Flatten(name='FlattenUser')(user_emb)

    user_model = keras.Model(inputs=user_input, outputs=user_vec)
    
    merged = layers.Dot(name = 'dot_product', normalize = True, axes = 2)([movie_emb, user_emb])
    merged_dropout = layers.Dropout(0.2)(merged)
    
    
    dense_1 = layers.Dense(70,name='FullyConnected-1')(merged)
    dropout_1 = layers.Dropout(0.2,name='Dropout_1')(dense_1)

    dense_2 = layers.Dense(50,name='FullyConnected-2')(dropout_1)
    dropout_2 = layers.Dropout(0.2,name='Dropout_2')(dense_2)

    dense_3 = keras.layers.Dense(20,name='FullyConnected-3')(dropout_2)
    dropout_3 = keras.layers.Dropout(0.2,name='Dropout_3')(dense_3)

    dense_4 = keras.layers.Dense(10,name='FullyConnected-4', activation='relu')(dropout_3)

    result = layers.Dense(1, name='result', activation="relu") (dense_4)

    adam = keras.optimizers.Adam(learning_rate=0.001)
    model = keras.Model([movie_input, user_input], result)
    model.compile(optimizer=adam,loss= 'mean_absolute_error')
    return model, movie_model, user_model

## adjusted language
def EmbeddingRec(emb_size, num_items, num_users, train):
    row_count=len(train)
    beer_input = keras.Input(shape=(1,), name='beer_id')

    beer_emb = layers.Embedding(output_dim=emb_size, input_dim=num_items, input_length=row_count, name='beer_emb')(beer_input)
    beer_vec = layers.Flatten(name='FlattenBeer')(beer_emb)

    beer_model = keras.Model(inputs=beer_input, outputs=beer_vec)
    
    user_input = keras.Input(shape=(1,), name='user_id')

    user_emb = layers.Embedding(output_dim=emb_size, input_dim=num_users, input_length=row_count, name='user_emb')(user_input)
    user_vec = layers.Flatten(name='FlattenUser')(user_emb)

    user_model = keras.Model(inputs=user_input, outputs=user_vec)
    
    merged = layers.Dot(name = 'dot_product', normalize = True, axes = 2)([beer_emb, user_emb])
    merged_dropout = layers.Dropout(0.2)(merged)
    
    
    dense_1 = layers.Dense(70,name='FullyConnected-1')(merged)
    dropout_1 = layers.Dropout(0.2,name='Dropout_1')(dense_1)

    dense_2 = layers.Dense(50,name='FullyConnected-2')(dropout_1)
    dropout_2 = layers.Dropout(0.2,name='Dropout_2')(dense_2)

    dense_3 = keras.layers.Dense(20,name='FullyConnected-3')(dropout_2)
    dropout_3 = keras.layers.Dropout(0.2,name='Dropout_3')(dense_3)

    dense_4 = keras.layers.Dense(10,name='FullyConnected-4', activation='relu')(dropout_3)

    result = layers.Dense(1, name='result', activation="relu") (dense_4)

    adam = keras.optimizers.Adam(learning_rate=0.001)
    model = keras.Model([beer_input, user_input], result)
    model.compile(optimizer=adam,loss= 'mean_absolute_error', metrics= tf.keras.metrics.RootMeanSquaredError())
    return model, beer_model, user_model

def KerasEvaluate(model,train,test): #numpy version
    pred = model.predict(test)
    a=pred.argsort(axis=1) #ascending, sort by row, return index
    a = np.fliplr(a) #reverse to get descending
    a = a[:,0:10] #return only the first 10 columns of each row
    Ybool = [] #initialze 2D arrray
    for t, idx in enumerate(a):
        ybool = np.zeros(num_items +1) #zero fill; 0 index is reserved
        ybool[idx] = 1 #flip the recommended item from 0 to 1
        Ybool.append(ybool)
    A = map(lambda t: list(t), Ybool)
    right_sum = (A * test).max(axis=1) #element-wise multiplication, then find the max
    right_sum = right_sum.sum() #how many times did we score a hit?
    return right_sum/len(test) #fraction of observations where we scored a hit

def KerasEvaluator(model,train,test):
  test_user_item_set = set(zip(test['user_id'], test['beer_beerid']))

  # Dict of all items that are interacted with by each user
  user_interacted_items = df.groupby('user_id')['beer_beerid'].apply(list).to_dict()

  hits = []

  for (u,i) in test_user_item_set:
      interacted_items = user_interacted_items[u]
      not_interacted_items = set(all_beerIds) - set(interacted_items)
      selected_not_interacted = list(np.random.choice(list(not_interacted_items), 99))
      test_items = selected_not_interacted + [i]
      
      predicted_labels = user_model.predict([u]).reshape(1,-1)[0]
      
      top10_items = [test_items[i] for i in np.argsort(predicted_labels)[0:10].tolist()]
      
      if i in top10_items:
          hits.append(1)
      else:
          hits.append(0)
          
  print("The Hit Ratio @ 10 is {:.2f}".format(np.average(hits)))

"""## Training"""

num_users = df['user_id'].max()+1
num_items = df['beer_beerid'].max()+1
all_beerIds = df['beer_beerid'].unique()

model, beer_model, user_model=EmbeddingRec(30, num_items,num_users,train)

callbacks = [keras.callbacks.EarlyStopping('val_loss', patience=10),
             keras.callbacks.ModelCheckpoint('besttest', save_best_only=True)]

history2 = model.fit([train.beer_beerid.values, train.user_id.values],train.review_overall.values, batch_size=1000,
                              epochs =50, validation_split =.2,
                              verbose = 1,
                              callbacks=callbacks)

"""## Save and Load"""

# Save
#model.save(path+'KerasBest')

# Load
model2 = keras.models.load_model(path+'KerasBest')

"""## Plot

### shape
"""

keras.utils.plot_model(model2, show_shapes=True)

"""### loss"""

from pylab import rcParams
rcParams['figure.figsize'] = 10, 5
import matplotlib.pyplot as plt
plt.plot(history.history['loss'] , 'g')
plt.title('model loss')
plt.ylabel('loss')
plt.xlabel('epochs')
plt.legend(['train'], loc='upper right')
plt.grid(True)
plt.show()

# KNN recommendation
test_user_ID = 200
test_item_ID = 123

import collections

# extract movie embedding
item_embedding_list = []
item_embed_map = collections.defaultdict()

for _id in all_beerIds:
    emb = beer_model.predict(np.array([_id]))
    val = list(emb.reshape(1,-1))[0]
    item_embedding_list.insert(_id, val)
    item_embed_map[_id] = val

"""## Evaluate"""



def recommend_movies(embedding):
    distances, indices = clf.kneighbors(embedding.reshape(1, -1),  n_neighbors=10)
    indices = indices.reshape(10,1)
    df_indices = pd.DataFrame(indices, columns = ['beer_beerid'])
    return df_indices.merge(movies,on='beer_beerid',how='inner',suffixes=['_u', '_m'])['title']

predicted_labels[0:10]

for (u,i) in test_user_item_set:
      interacted_items = user_interacted_items[u]
      not_interacted_items = set(all_beerIds) - set(interacted_items)
      selected_not_interacted = list(np.random.choice(list(not_interacted_items), 99))
      test_items = selected_not_interacted + [i]
      
      predicted_labels = user_model.predict([u]).reshape(1,-1)[0]
      
      top10_items = [test_items[i] for i in np.argsort(predicted_labels)[0:10].tolist()]
      
      if i in top10_items:
          hits.append(1)
      else:
          hits.append(0)
          
  print("The Hit Ratio @ 10 is {:.2f}".format(np.average(hits)))

def tsne_plot(model, item_embedding_list, size = num_items):
    tsne_model = TSNE(perplexity=40, n_components=2, init='pca', n_iter=2500, random_state=23)
    new_values = tsne_model.fit_transform(item_embedding_list[:size])
    x = []
    y = []
    for value in new_values:
        x.append(value[0])
        y.append(value[1])
    labels = list(range(0,size))
    plt.figure(figsize=(16, 16)) 
    for i in range(len(x)):
        plt.scatter(x[i],y[i])
        plt.annotate(labels[i],xy=(x[i], y[i]),xytext=(5, 2),textcoords='offset points',ha='right',va='bottom')
    plt.show()

