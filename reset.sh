cat reset_password.sh 
#!/bin/bash

# Path to the file containing usernames
USER_FILE="username.txt"

# Output CSV file
CSV_FILE="passwords.csv"

# Container name
CONTAINER_NAME="domserver-web-2"

# DOMjudge directory inside the container
DOMJUDGE_DIR="/opt/domjudge/domserver"

# Command to reset password
RESET_CMD="webapp/bin/console domjudge:reset-user-password"

# Initialize CSV file with header
echo "Username,Password" > "$CSV_FILE"

# Read the file line by line
while IFS= read -r username || [[ -n "$username" ]]; do
    echo "$username";
done < "$USER_FILE"



echo "Password reset process completed. Saved to $CSV_FILE."
