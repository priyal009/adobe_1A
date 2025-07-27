
# Use a lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy all files from your project folder to /app
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Default command to run the Python script with a sample file
CMD ["python", "main.py"]
