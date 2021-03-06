from pyspark.ml import Pipeline
from pyspark.ml.regression import LinearRegression
from pyspark.ml.regression import LinearRegressionModel
from pyspark.ml.feature import VectorAssembler, OneHotEncoder
from pyspark.sql import SparkSession
from pyspark import SparkContext
from pyspark.ml.feature import StringIndexer
from pyspark.ml.feature import OneHotEncoder
from pyspark.ml import PipelineModel
import findspark
import pyspark
from pyspark2pmml import PMMLBuilder
import pandas as pd


class Model_maker:
    """ This cass will handle the making model and transforming data in Spark. The spark must be installed
    and be prepared for using. It contains the set_model function in which model will be trained,
    prediction_module that use the trained model to estimate the expenditures. Save and load model that will
    save and load the pipelines or ML models"""

    def __init__(self):
        self.ml_model = None
        self.p_model = None
        self.data = None

    # Initializing the spark and spark context for using them during the processing
    @staticmethod
    def spark_init():
        findspark.init()
        spark_path = findspark.find()
        print("Spark is located at: " + spark_path)
        spark = SparkSession.builder.appName('Techno_Pred').getOrCreate()
        sc = spark.sparkContext
        sc.setLogLevel("FATAL")
        return spark, sc

    # Make the model, Also transforming the data throughout the spark pipeline
    # The pipeline contains StringIndexer, one hot cding, and vector assembler
    def set_model(self, data, spark, loaded_p_model=None):
        self.data = data

        # Convert the input data (pandas data frame) to the spark data frame for further preprocessing
        data = spark.createDataFrame(self.data)
        print("Transform the Data to Spark Dataframe.")
        print("Data Schema: ")
        data.printSchema()
        string_indexer_dic = {}

        # check the variables which are string to the pipeline process on them
        string_feature_list = []
        for col in data.columns:
            if col == 'label':
                continue
            elif pyspark.sql.types.StringType == type(data.schema[col].dataType):
                string_feature_list.append(col)
        new_list = []
        for something in string_feature_list:
            new_list.append(something + "_index")
        use_less_columns = new_list + string_feature_list

        # If the method does not have the model as input (it means that we want to make a new model)
        # will satisfy this condition and will go through it.
        if loaded_p_model is None:

            # Make the dictionary for saving the transform structure (Using StringIndexer)
            for str_column in string_feature_list:
                string_indexer_dic["%s_index" % str_column] = StringIndexer(inputCol=str_column,
                                                                            outputCol=str_column + "_index")
            # Convert string indexer dic to list cause the pipeline accept the list.
            string_indexer_list = [string_indexer_dic[indexer_item] for indexer_item in string_indexer_dic]

            # Make the dictionary for saving the transform structure (Using OneHotCoding)
            string_ohc_dic = {}
            for str_column_next in string_feature_list:
                string_ohc_dic["%s_ohc" % str_column_next] = OneHotEncoder(inputCol=str_column_next + "_index",
                                                                           outputCol=str_column_next + "_ohc")

            # Convert "one hot coding" dic to list cause the pipeline accept the list.
            indexed_ohc_list: list[OneHotEncoder] = [string_ohc_dic[indexer_item] for indexer_item in string_ohc_dic]

            # Add all the stages to the pipeline together
            print("Add the stages to the pipeline")
            stages = string_indexer_list + indexed_ohc_list
            pipeline = Pipeline(stages=stages)

            # fit the pipeline with model to prepare it for the next usages
            pipeline_model = pipeline.fit(data)
            print("Executing the transformation throughout the pipeline")
            data = pipeline_model.transform(data)

            # Make the tuple from the first columns that we change them.
            string_indexer_tuple = tuple(use_less_columns)
            data = data.drop(*string_indexer_tuple)
            feature_list = []
            for col in data.columns:
                if col == 'label':
                    continue
                else:
                    feature_list.append(col)

            # Change the data to feature vector as a input for the Ml model
            print("Vector Assembler is working ...")
            assembler = VectorAssembler(inputCols=feature_list, outputCol="features")
            data = assembler.transform(data)
            data = data.select(['features', 'label'])
            print("Samples of feature vectors")
            data.show(5)

            # initialize the linear regression model
            lr = LinearRegression(featuresCol='features', labelCol='label',
                                  maxIter=10, regParam=0.3, elasticNetParam=0.8)
            splits = data.randomSplit([0.7, 0.3])
            train_df = splits[0]
            test_df = splits[1]
            lr_model = lr.fit(train_df)
            print("Coefficients: " + str(lr_model.coefficients))
            print("Intercept: " + str(lr_model.intercept))
            test_result = lr_model.evaluate(test_df)
            training_summary = lr_model.summary
            print("========================================================")
            print('Model has been made')
            print("Root Mean Squared Error (RMSE)"
                  " on test data = %g" % training_summary.rootMeanSquaredError)
            print("Root Mean Squared Error (RMSE)"
                  " on test data = %g" % test_result.rootMeanSquaredError)
            print("========================================================")

        # if we pass a model to this method it will do this section which in fact is a data refiner
        # in means that it will give the model (pipeline model) and do the pipline transmigration on
        # that and return the refined data for using in model. In fact this part will use when we want
        # to use a predefined model
        else:
            tdata = loaded_p_model.transform(data)
            pipeline_model = None
            lr_model = None
            string_indexer_tuple = tuple(use_less_columns)
            tdata = tdata.drop(*string_indexer_tuple)
            feature_list = []
            for col in tdata.columns:
                if col == 'label':
                    continue
                else:
                    feature_list.append(col)
            print("Vector Assembler is working ...")
            assembler = VectorAssembler(inputCols=feature_list, outputCol="features")
            tdata = assembler.transform(tdata)
            tdata = tdata.select(['features'])
            print("Samples of feature vectors")
            tdata.show(5)
            data = tdata

        return pipeline_model, lr_model, data

    # save the pipline model
    def save_p_model(self, p_model, p_model_path):
        self.p_model = p_model
        self.p_model.write().save(p_model_path)
        # Should use pmmlBuilder

    # save the ml model
    def save_ml_model(self, ml_model, ml_model_path):
        self.ml_model = ml_model
        self.ml_model.write().save(ml_model_path)

    # will get the refined data generate from set_model method and a model and return the prediction
    @staticmethod
    def prediction_module(refine_data, ml_model):
        ml_prediction = ml_model.transform(refine_data)
        ml_prediction.show()
        predicted_df = ml_prediction.toPandas()
        return predicted_df

    # load pipeline model
    @staticmethod
    def load_p_model(r_p_model_path):
        read_pipeline = PipelineModel.load(r_p_model_path)
        return read_pipeline

    # load ML model
    @staticmethod
    def load_ml_model(r_ml_model_path):
        read_ml_model = LinearRegressionModel.load(r_ml_model_path)
        return read_ml_model

