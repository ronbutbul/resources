curl -X POST -H "Content-Type: application/json" --data '
{"name": "mongo5-test-source",
  "config": {
         "connector.class": "com.mongodb.kafka.connect.MongoSourceConnector",
         "connection.uri": "mongodb://ec2-16-171-153-234.eu-north-1.compute.amazonaws.com:27017",
         "database": "kafka_test",
         "collection": "test",
	 "topic.prefix": "aaaa",
	 "errors.tolerance": "none",
	 "errors.log.enable":true,
         "errors.log.include.messages":true
}}' http://localhost:39631/connectors -w "\n"
