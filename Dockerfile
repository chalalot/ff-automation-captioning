# 1. Pick a Python version (just like you have Python installed on your laptop)
FROM python:3.11-slim

# 2. Create a folder inside the container to hold your app
WORKDIR /app

# 3. Copy only requirements first (this optimizes build speed)
COPY requirements.txt .

# 4. Run the install command (Your step 1)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your app code into the container
COPY . .

# 6. Tell Docker that this app will listen on port 8501
EXPOSE 8501

# 7. The command to start the app (Your step 2)
# IMPORTANT: You must add --server.address=0.0.0.0 so it listens to the outside world
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]