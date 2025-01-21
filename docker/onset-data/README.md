# Data loading

## qlever

For dbpedia:
```sh
pip install qlever
git clone git@github.com:ad-freiburg/qlever.git
git switch quotes-in-irirefs
docker build -t qlever:quotes . 
cd ..
mkdir -p qlever-data

qlever setup-config dbpedia
qlever get-data #if we don't have the data present, however, if the data is already downloaded data copy it to qlever-data/rdf-input and skip this command
qlever index --image qlever:quotes
qlever start --image qlever:quotes
#qlever stop --image qlever:quotes
```