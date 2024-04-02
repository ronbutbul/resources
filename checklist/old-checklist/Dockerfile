# Use an official Python runtime as a base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the Python script and the JSON configuration file into the container
COPY oc-script.py .
COPY oc-config.json .

# Install any needed packages specified by your script
# For example, pymongo for MongoDB connectivity
RUN pip install pymongo
RUN pip install redis
RUN pip install kafka-python
# Command to run the script
CMD ["python", "./check_mongo.py"]
