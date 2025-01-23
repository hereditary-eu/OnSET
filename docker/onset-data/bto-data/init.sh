
tdb2.tdbloader --loader=parallel --loc ../fuseki-data/databases/bto *.ttl
# tdb2.tdbloader --loader=parallel --loc ../fuseki-data/databases/bto *.ttl.zip
# tdb2.tdbloader --loader=parallel --loc ../fuseki-data/databases/dbpedia *.bz2
# tdb2.tdbstats --loc=../fuseki-data/databases/dbpedia > /tmp/stats.opt 
# mv /tmp/stats.opt > ../fuseki-data/databases/dbpedia/Data-0001/

# lbunzip2 *.bz2
# lbunzip2 *.bzip2
# rename.ul .ttl.bzip2.out .ttl  *.ttl.bzip2.out
# rm -rf ../graphdb-import/dbpedia
# mkdir ../graphdb-import/dbpedia
# mv *.ttl ../graphdb-import/dbpedia/    
# mv *.nt ../graphdb-import/dbpedia/    
# docker run \
# 	-v ./staging:/staging \
# 	-v ./fuseki-data:/fuseki \
#    stain/jena-fuseki ./load.sh 