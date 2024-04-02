# Use an official Python runtime as a base image
FROM python:3.9-slim

RUN apt-get update && \
  apt-get install -y apt-transport-https gnupg curl && \
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
  install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
  rm kubectl && \
  apt-get clean


# Copy the Python script and the JSON configuration file into the container
COPY prototype.py .

# Install any needed packages specified by your script
# For example, pymongo for MongoDB connectivity
RUN pip install pymongo
RUN pip install kubernetes
RUN pip install requests
RUN pip install PyYAML
# Command to run the script
CMD ["python", "./prototype.py"]
