#!/bin/bash
rm -rf bto 
mkdir -p bto
cd bto
wget ${DATABUS_URL}
cd ..
riot --merge --output=NT bto/bto.ttl ../../data/datasets/BRAINTEASER_ALS_MS_datasets/**/*.ttl > bto/bto.nt