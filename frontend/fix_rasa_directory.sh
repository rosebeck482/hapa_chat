#!/bin/bash

# Script to fix the Rasa project directory name

# Check if the directory with a space exists
if [ -d "Supabase/functions/rasa_project /" ]; then
    echo "Found directory with space: Supabase/functions/rasa_project /"
    echo "Renaming to: Supabase/functions/rasa_project"
    
    # Create the target directory if it doesn't exist
    mkdir -p Supabase/functions/rasa_project
    
    # Copy all files from the source to the target
    cp -R "Supabase/functions/rasa_project /"* Supabase/functions/rasa_project/
    
    echo "Files copied successfully."
    echo "You can now use the Rasa project at: Supabase/functions/rasa_project"
else
    echo "Directory 'Supabase/functions/rasa_project /' not found."
    echo "Checking for alternative directory names..."
    
    # List directories in Supabase/functions to help identify the correct one
    echo "Directories in Supabase/functions:"
    ls -la Supabase/functions/
fi

echo "Done." 