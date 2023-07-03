#!/usr/bin/env bash

# Install Runner as a global dotnet tool

cd ModelsAnalyzer/Runner
dotnet pack --configuration Release
dotnet tool install --global --add-source ./package RenodeAnalyzersRunner

# run this command to remove the tool
# dotnet tool uninstall -g RenodeAnalyzersRunner