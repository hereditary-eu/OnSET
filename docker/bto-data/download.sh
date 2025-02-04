#!/bin/zsh
rm -rf bto 
mkdir -p bto
cd bto
wget https://zenodo.org/records/12789731/files/bto.ttl
cd ..
riot --merge --output=NT bto/bto.ttl ../../data/datasets/BRAINTEASER_ALS_MS_datasets/**/*.ttl > bto/bto.nt