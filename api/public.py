#!/usr/bin/env python3
# -*- coding:utf-8 -*-
###
# *********************************************************************
# |                                                                    
# | File: \public.py
# | Description: <<desc here>>
# | Project: api
# | Created Date: 25th May 2020
# | Author: Alban Shahaj (shahaal)
# | Email: data.collection@efsa.europa.eu
# | -----------------------------------------------------------------  
# | Last Modified: Thursday, 24th June 2020
# | Modified By: Alban Shahaj (shahaal)
# | -----------------------------------------------------------------  
# | Copyright (c) 2020 European Food Safety Authority (EFSA)
# |                                                                    
# *********************************************************************
###

from . import api, c

from nltk.tokenize import word_tokenize
from flask import request
import spacy, json, re


rootPath = "api/asset/"
# for production
models_path = "/work-dir/"
# TODO only debug
# models_path = rootPath + "models/"

# initialise all possible models name
global possibleModels

possibleModels = ["BT", "CAT"]
# create list facets
possibleModels.extend([
    "F" + "{:02}".format(i) for i in range(1, 34)
    if i not in [5, 13, 14, 15, 16, 29, 30]
])

'''
# TODO only debug
possibleModels = ["BT", "CAT", "F03"] #, "F04", "F10", "F22", "F26", "F28"]
'''

# load the models from the external file
global models
models = {}
for modelName in possibleModels:
    print("loadModel: "+modelName, flush=True)
    models[modelName] = spacy.load(models_path+modelName)


# remove punctuation, stop words and not
punctuation = r"[!()\-[\]{};:‘“”ªˆ©¤€÷×–¿•…´`'\"\\,<>./?@#$^&*_~=’+°]"
# read custom stop words list
stopWords = []
with open(rootPath+'data/stop_words.csv', 'r') as f:
    stopWords = f.read().split('\n')

# create queries
query_terms = "SELECT * FROM terms WHERE termCode IN (%s) LIMIT 100"
query_attrs = "SELECT * FROM attributes WHERE code IN (%s) LIMIT 100"


"""
def filterDuplicates(tokens):
    ''' filter duplicated words maintaining the order '''

    return sorted(set(tokens), key=tokens.index)
"""

def filter_duplicates(tokens):
    ''' filter duplicated words maintaining the order '''

    return sorted(set(tokens), key=tokens.index)


def clean_text(x):
    ''' method used fro cleaning text given in input '''

    # all lower case
    clean_str = x.lower()
    # remove punctuation
    clean_str = re.sub(punctuation, " ", clean_str)
    # tokenization
    tokens = word_tokenize(clean_str)

    # remove duplicates
    tokens = filter_duplicates(tokens)

    # remove duplicates
    # tokens = filterDuplicates(tokens)
    # remove stop words
    tokens = [w for w in tokens if not w in stopWords]

    # enable/disable normalization
    # normalizedStr = normalise(cleanStr, verbose=False)

    # trim multiple white spaces
    clean_str = ' '.join(tokens)

    return clean_str


def get_top(text, nlp, t):
    global models
    # for each class create the tuple <classCode, classProb>
    tuples = models[nlp](text).cats

    # sort in decreasing order and keep only first 100
    tuples = sorted(
        tuples.items(), key=lambda item: item[1], reverse=True)[:100]

    # chose from which library to get the name
    query = query_terms if nlp != "CAT" else query_attrs
    
    # initialise results to return
    data_json = {}
    # keep only codes above threshold
    predictions = [(k,v) for k,v in tuples if v>=t]
    
    # if list of results is empty
    if not predictions:
        return data_json

    # rebuild query based on results
    query = (query % ','.join('?'*len(predictions)))
    # execute query
    c.execute(query, [i[0] for i in predictions])
    # get column names
    header = [i[0] for i in c.description]
    # get records from db
    data = c.fetchall()
    # build json
    for i in data:
        d = dict(zip(header[1:], i[1:]))
        d.update({"acc": v for k,v in predictions if k==i[0]})
        data_json[i[0]]=d
        
    return data_json


@api.route("/predict", methods=["GET"])
def predict():
    '''
    @shahaal
    flask API service which return the results given from the model specified in input
    '''
    # get from request the given free text by key
    text = request.args.get("text")
    # get from request the requested model to activate
    model = request.args.get("model").upper()
    # get the treshold from the request
    t = float(request.args.get("threshold"))

    # if the requested model is not available
    if model not in possibleModels:
        return json.dumps("{}")

    # pre process the inserted free text
    text = clean_text(text)

    # get top predictions sorted by prob
    res = {model: get_top(text, model, t)}

    # return as json
    return json.dumps(res)


@api.route("/predict_all", methods=["GET"])
def predict_all():
    '''
    @shahaal
    flask API service which return the results of all models by passing the given free text
    '''
    # get from request the given free text by key
    text = request.args.get("text")
    # get the treshold from the request
    t = float(request.args.get("threshold"))

    # pre process the inserted free text
    text = clean_text(text)

    # predict possible baseterms
    bt_res = get_top(text, 'BT', t)
    
    # predict possible facet categories
    fc_res = get_top(text, 'CAT', t)
    
    # predict possible facets per each category
    for cat_code in fc_res.keys():
        # append the list of predicted facets
        fc_res[cat_code].update({"facets": get_top(text, cat_code, t)})

    # build final json obj
    final_json = {"bt": bt_res, "cat": fc_res}
    # Merge the dicts as json
    return json.dumps(final_json)