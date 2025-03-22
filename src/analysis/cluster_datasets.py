from typing import List, Tuple
from sklearn.cluster import AgglomerativeClustering
from src.model.geo_dataset import GEODataset
from src.analysis.vectorize_datasets import vectorize_datasets
from sklearn.metrics import silhouette_score
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer
from scipy.sparse import spmatrix
import numpy as np
import time

SVD_COMPONENTS = 15


def get_clusters_top_terms(
    embeddings: spmatrix, clusters: List[int], vocabulary: List[str]
) -> List[List[str]]:
    """
    Identifies key descriptive words for each cluster by analyzing the
    distribution of TF-IDF values in dataset descriptions. Words are ranked
    based on how closely the sums of their TF-IDF in each cluster match a
    reference pattern where each word is strongly associated with a single
    cluster ([0, ..., 0, 1, 0, ..., 0] vector). This similiraty is measured
    using cosine_similarity.

    Based on _get_topics_description_cosine from PubTrends.

    :param embeddings: Vector representations of the datasets.
    :param clusters: Cluster assignments for each dataset.
    :param vocabulary: Vocabulary of the datasets.
    :return: List of lists of most influential terms for every cluster.
    """

    n_clusters = np.max(clusters) + 1
    word_tf_idf_per_cluster = np.zeros((n_clusters, embeddings.shape[1]))
    for i in range(n_clusters):
        word_tf_idf_per_cluster[i] = np.sum(embeddings[clusters == i], axis=0)

    tf_idf_norm = np.sqrt(np.diag(word_tf_idf_per_cluster.T @ word_tf_idf_per_cluster))
    word_tf_idf_per_cluster = word_tf_idf_per_cluster / tf_idf_norm

    # Calculate cosine distance between the tf-idf vector and [0, ..., 0, 1, 0, ..., 0] for each cluster
    cluster_mask = np.eye(n_clusters)
    distance = word_tf_idf_per_cluster.T @ cluster_mask
    total_tf_idf = np.sum(embeddings, axis=0)
    total_tf_idf = np.squeeze(np.asarray(total_tf_idf))

    # Adjust cosine distances by tf-idf across the corpus so super rare words don't come out on top
    adjusted_distance = distance.T * np.log1p(total_tf_idf)

    top_term_indices_per_cluster = adjusted_distance.argsort()[:, ::-1]
    top_terms = []
    for i in range(n_clusters):
        top_terms.append([])
        for ind in top_term_indices_per_cluster[i, :10]:
            top_terms[-1].append(vocabulary[ind])

    return top_terms


def cluster_datasets(
    embeddings: spmatrix, n_clusters: int
) -> Tuple[List[int], np.ndarray]:
    """
    Clusters the vector representations of GEO datasets.

    :param embeddings: Vector representations of the datasets.
    :param n_cluster: Number of clusters to create.
    :return: Tuple (Cluster assignments for each dataset, Cluster centroids)
    """

    clusterer = AgglomerativeClustering(n_clusters=n_clusters)

    cluster_assignments = clusterer.fit_predict(embeddings)
    silhouette_avg = silhouette_score(embeddings, cluster_assignments)
    print(f"Silhouette score: {silhouette_avg}")

    return cluster_assignments, clusterer


if __name__ == "__main__":
    from src.ingestion.download_geo_datasets import download_geo_datasets

    with open("ids.txt") as file:
        pubmed_ids = map(int, file)
        datasets = download_geo_datasets(pubmed_ids)
        # We filter out the 
        #datasets = list(filter(lambda dataset: dataset.is_not_superseries(), datasets))

        embeddings, vocabulary = vectorize_datasets(datasets)
        lsa = make_pipeline(
            TruncatedSVD(n_components=SVD_COMPONENTS, random_state=42),
            Normalizer(copy=False),
        )
        embeddings_svd = lsa.fit_transform(embeddings)
        explained_variance = lsa[0].explained_variance_ratio_.sum()
        print(f"Explained variance of the SVD step: {explained_variance * 100:.1f}%")

        begin = time.time()
        labels, centroids = cluster_datasets(embeddings_svd, 10)
        end = time.time()
        print("Clustering time:", end-begin)
        topics = get_clusters_top_terms(embeddings, labels, vocabulary)
        for i in range(len(topics)):
            print(f"Cluster {i} topics: {' '.join(topics[i])}")
