# -*- coding:utf-8 -*-
import tensorflow as tf

from ..feature_column import build_input_features, get_linear_logit, input_from_feature_columns
from ..layers.core import PredictionLayer, DNN
from ..layers.interaction import DestineLayer
from ..layers.utils import concat_func, add_func, combined_dnn_input

from deepctr.models.pairwise import Pairwise


def DESTINE(linear_feature_columns, dnn_feature_columns, att_layer_num=3, att_embedding_size=8, att_head_num=2,
            att_res=True,
            dnn_hidden_units=(256, 256), dnn_activation='relu', l2_reg_linear=1e-5,
            l2_reg_embedding=1e-5, l2_reg_dnn=0, dnn_use_bn=False, dnn_dropout=0, seed=1024,
            task='binary', model_mode='point'):
    """Instantiates the DESTINE Network architecture.

    :param dnn_feature_columns: An iterable containing all the features used by deep part of the model.
    :param att_layer_num: int.The InteractingLayer number to be used.
    :param att_embedding_size: int.The embedding size in multi-head self-attention network.
    :param att_head_num: int.The head number in multi-head  self-attention network.
    :param att_res: bool.Whether or not use standard residual connections before output.
    :param dnn_hidden_units: list,list of positive integer or empty list, the layer number and units in each layer of DNN
    :param dnn_activation: Activation function to use in DNN
    :param l2_reg_linear: float. L2 regularizer strength applied to linear part
    :param l2_reg_embedding: float. L2 regularizer strength applied to embedding vector
    :param l2_reg_dnn: float. L2 regularizer strength applied to DNN
    :param dnn_use_bn:  bool. Whether use BatchNormalization before activation or not in DNN
    :param dnn_dropout: float in [0,1), the probability we will drop out a given DNN coordinate.
    :param seed: integer ,to use as random seed.
    :param task: str, ``"binary"`` for  binary logloss or  ``"regression"`` for regression loss
    :return: A Keras model instance.
    """

    use_bias = model_mode == 'point'

    if len(dnn_hidden_units) <= 0 and att_layer_num <= 0:
        raise ValueError("Either hidden_layer or att_layer_num must > 0")

    features = build_input_features(dnn_feature_columns)
    inputs_list = list(features.values())

    linear_logit = get_linear_logit(features, linear_feature_columns, seed=seed, prefix='linear', l2_reg=l2_reg_linear)

    sparse_embedding_list, dense_value_list = input_from_feature_columns(features, dnn_feature_columns,
                                                                         l2_reg_embedding, seed)

    att_input = concat_func(sparse_embedding_list, axis=1)

    for _ in range(att_layer_num):
        att_input = DestineLayer(
            att_embedding_size, att_head_num, att_res)(att_input)
    att_output = tf.keras.layers.Flatten()(att_input)

    dnn_input = combined_dnn_input(sparse_embedding_list, dense_value_list)

    if len(dnn_hidden_units) > 0 and att_layer_num > 0:  # Deep & Interacting Layer
        deep_out = DNN(dnn_hidden_units, dnn_activation, l2_reg_dnn, dnn_dropout, dnn_use_bn, seed=seed, train_bias=use_bias)(dnn_input)
        stack_out = tf.keras.layers.Concatenate()([att_output, deep_out])
        final_logit = tf.keras.layers.Dense(
            1, use_bias=False, kernel_initializer=tf.keras.initializers.glorot_normal(seed))(stack_out)
    elif len(dnn_hidden_units) > 0:  # Only Deep
        deep_out = DNN(dnn_hidden_units, dnn_activation, l2_reg_dnn, dnn_dropout, dnn_use_bn, seed=seed, train_bias=use_bias)(dnn_input, )
        final_logit = tf.keras.layers.Dense(
            1, use_bias=False, kernel_initializer=tf.keras.initializers.glorot_normal(seed))(deep_out)
    elif att_layer_num > 0:  # Only Interacting Layer
        final_logit = tf.keras.layers.Dense(
            1, use_bias=False, kernel_initializer=tf.keras.initializers.glorot_normal(seed))(att_output)
    else:  # Error
        raise NotImplementedError

    final_logit = add_func([final_logit, linear_logit])

    output = PredictionLayer(task, use_bias=use_bias)(final_logit)

    if model_mode == 'index':
        model = tf.keras.models.Model(inputs=inputs_list, outputs=[output, stack_out])
    elif model_mode == 'point':
        model = tf.keras.models.Model(inputs=inputs_list, outputs=output)
    else:
        model = Pairwise(inputs=inputs_list, outputs=output)

    return model
