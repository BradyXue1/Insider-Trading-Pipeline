# Use a slim version of Python to keep the container small
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy your requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Keep the container running so we can exec into it
CMD ["tail", "-f", "/dev/null"]