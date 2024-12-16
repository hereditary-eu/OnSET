<script setup lang="ts">

</script>

<template>
  <main>
    <h2 class="heading">Welcome to the Ontology and Sparse data Exploration Tool (OnSET) v0.1</h2>
    <p>
      The Ontology and Semantic data Exploration Tool (OnSET) is a web-based tool that allows users to explore and analyze ontologies and related sparse data sets. It automatically maps arbitrary datasets onto ontologies and provides a user-friendly interface for exploring the data and ontology relationships. OnSET is designed to be extensible and customizable, allowing users to add new ontologies and data sets as needed.
    </p>
    <RouterLink to="/graph">Start Exploration!</RouterLink>
  </main>
</template>
<style scoped>
main {
  padding: 0 var(--section-gap);
  margin: 0 auto;
}
h1 {
  font-weight: 500;
  font-size: 2.6rem;
  position: relative;
  top: -10px;
}

.heading {
  display: flex;
  justify-items: center;
  justify-content: center;
}
</style>