# Copyright © 2018 Battelle Memorial Institute
# All rights reserved.
from __future__ import annotations

import pickle
import warnings
from collections import OrderedDict
from typing import Optional, Any

import networkx as nx
import numpy as np
import pandas as pd
from networkx.algorithms import bipartite
from scipy.sparse import coo_matrix, csr_matrix

from hypernetx.classes import Entity, EntitySet
from hypernetx.exception import HyperNetXError, NWHY_WARNING
from hypernetx.utils.decorators import warn_nwhy

__all__ = ["Hypergraph"]


class Hypergraph:
    """
    ======================
    Hypergraphs in HNX 2.0
    ======================

    An hnx.Hypergraph H = (V,E) references a pair of disjoint sets:
    V = nodes (vertices) and E = (hyper)edges.

    HNX allows for multi-edges by distinguishing edges by 
    their identifiers instead of their contents. For example let      
    V = {1,2,3} and E = {e1,e2,e3},  
    where e1 = {1,2}, e2 = {1,2}, and e3 = {1,2,3}.
    The edges e1 and e2 contain the same set of nodes and yet
    are distinct and are distinguishable within H = (V,E).

    New as of version 2.0, HNX provides methods to easily store and  
    access additional metadata such as cell, edge, and node weights. 
    Metadata associated with (edge,node) incidences
    are referenced as **cell_properties**. 
    Metadata associated with a single edge or node is referenced 
    as its **properties**. 

    The fundamental object needed to create a hypergraph is a **setsystem**. The
    setsystem defines the many to many relationships between edges and nodes in
    the hypergraph. Cell properties for the incidence pairs can be defined within 
    the setsystem or in a separate pandas.Dataframe or dict. 
    Edge and node properties are defined with a pandas.DataFrame or dict.

    SetSystems
    ----------
    There are five types of setsystems currently accepted by the library. 

    1.  **iterable of iterables** : Barebones hypergraph uses Pandas default 
        indexing to generate hyperedge ids. Elements must be hashable.: ::

        >>> H = Hypergraph([{1,2},{1,2},{1,2,3}])

    2.  **dictionary of iterables** : the most basic way to express many to many 
        relationships providing edge ids. The elements of the iterables must be
        hashable): ::

        >>> H = Hypergraph({'e1':[1,2],'e2':[1,2],'e3':[1,2,3]})

    3.  **dictionary of dictionaries**  : allows cell properties to be assigned
        to a specific (edge, node) incidence. This is particularly useful when 
        there are variable length dictionaries assigned to each pair: ::

        >>> d = {'e1':{ 1: {'w':0.5, 'name': 'related_to'},
        >>>             2: {'w':0.1, 'name': 'related_to', 
        >>>                 'startdate': '05.13.2020'}},
        >>>      'e2':{ 1: {'w':0.52, 'name': 'owned_by'},
        >>>             2: {'w':0.2}},
        >>>      'e3':{ 1: {'w':0.5, 'name': 'related_to'},
        >>>             2: {'w':0.2, 'name': 'owner_of'},
        >>>             3: {'w':1, 'type': 'relationship'}}
        
        >>> H = Hypergraph(d, cell_weight_col='w')

    4.  **pandas.DataFrame** For large datasets and for datasets with cell
        properties it is most efficient to construct a hypergraph directly from 
        a pandas.DataFrame. Incidence pairs are in the first two columns. 
        Cell properties shared by all incidence pairs can be placed in their own
        column of the dataframe. Variable length dictionaries of cell properties
        particular to only some of the incidence pairs may be placed in a single
        column of the dataframe. Representing the data above as a dataframe df:


        +-----------+-----------+-----------+-----------------------------------+
        |   col1    |   col2    |   w       |  col3                             |
        +-----------+-----------+-----------+-----------------------------------+
        |   e1      |   1       |   0.5     | {'name':'related_to'}             |
        +-----------+-----------+-----------+-----------------------------------+
        |   e1      |   2       |   0.1     | {"name":"related_to",             |
        |           |           |           |  "startdate":"05.13.2020"}        |
        +-----------+-----------+-----------+-----------------------------------+
        |   e2      |   1       |   0.52    | {"name":"owned_by"}               |
        +-----------+-----------+-----------+-----------------------------------+
        |   e2      |   2       |   0.2     |                                   |
        +-----------+-----------+-----------+-----------------------------------+
        |   ...     |   ...     |   ...     | {...}                             |
        +-----------+-----------+-----------+-----------------------------------+ 

        The first row of the dataframe is used to reference each column. ::

        >>> H = Hypergraph(df,edge_col="col1",node_col="col2",
        >>>                 cell_weight_col="w",misc_cell_properties="col3") 

    5.  **numpy.ndarray** For homogeneous datasets given in an ndarray a 
        pandas dataframe is generated and column names are added from the 
        column_names keyword argument. Cell properties containing multiple data
        types can be added with a separate dataframe or dict. ::

        >>> arr = np.array([['e1','1'],['e1','2'],
        >>>                 ['e2','1'],['e2','2'],
        >>>                 ['e3','1'],['e3','2'],['e3','3']])
        >>> H = hnx.Hoypergraph(arr, column_names=['col1','col2'])

    Edge and Node Properties
    ~~~~~~~~~~~~~~~~~~~~~~~~
    Properties specific to a single edge or node are passed through the 
    keywords: **edge_properties, node_properties, properties**.
    Properties may be passed as dataframes or dicts. 
    When a dataframe is passed to the edge_properties or node_properties, 
    the value assigned to edge_col and node_col is used to index the 
    properties. If a dataframe is passed as the properties keyword
    argument, then the first column must contain identifiers. This is useful
    if all nodes and edges have distinct uids or an object is used as both an
    edge and a node in the hypergraph and uses the same set of properties in
    both roles. Define the properties dataframe dfp: 

    +-----------+-----------+---------------------------------------+
    |   id      |   weight  |   properties                          |
    +-----------+-----------+---------------------------------------+
    |   1       |   1.2     |   {'color':'red'}                     |
    +-----------+-----------+---------------------------------------+
    |   2       |   .003    |   {'name':'Fido','color':'brown'}     |
    +-----------+-----------+---------------------------------------+
    |   3       |   1.0     |                                       |
    +-----------+-----------+---------------------------------------+
    |   e1      |   5.0     |   {'type':'event'}                    |
    +-----------+-----------+---------------------------------------+
    |   ...     |   ...     |   {...}                               |
    +-----------+-----------+---------------------------------------+

    OR with levels:

    +-------+-----------+-----------+---------------------------------------+
    | level |   id      |   weight  |   properties                          |
    +-------+-----------+-----------+---------------------------------------+
    |   1   |   1       |   1.2     |   {'color':'red'}                     |
    +-------+-----------+-----------+---------------------------------------+
    |   1   |   2       |   .003    |   {'name':'Fido','color':'brown'}     |
    +-------+-----------+-----------+---------------------------------------+
    |   1   |   3       |   1.0     |                                       |
    +-------+-----------+-----------+---------------------------------------+
    |   0   |   e1      |   5.0     |   {'type':'event'}                    |
    +-------+-----------+-----------+---------------------------------------+
    |   0   |   ...     |   ...     |   {...}                               |
    +-------+-----------+-----------+---------------------------------------+

    Then we pass it to the constructor as properties: ::

        >>> H = hnx.Hypergraph(df,properties=dfp) 

    Similarly, a properties dictionary with the format: ::

        dp = {id1 : {prop1:val1, prop2,val2,...}, id2 : ... }

    may be passed:
    ::
        >>> H = hnx.Hypergraph(d,properties=dp)


    Weights
    ~~~~~~~
    The default key for cell and object weights is "weight". The default value 
    is 1. Weights may be assigned and/or a new default prescribed in the 
    constructor using **cell_weight_col** and **cell_weights** for incidence pairs, 
    and using **edge_weight_prop, node_weight_prop, weight_prop, 
    default_edge_weight,** and **default_node_weight**. See parameters below for 
    details.

    Parameters
    ----------
    setsystem : (optional) dict of iterables, dict of dicts,iterable of iterables, 
        pandas.DataFrame, numpy.ndarray, default: None
        See SetSystem above for additional setsystem requirements.
    column_names : (optional) : Sequence[str], default : None
        used to assign as column names when setsystem is an ndarray or empty, 
        otherwise ignored.
    edge_col : (optional) int | str, default : 0
        column index (or name) in pandas.dataframe or numpy.ndarray, 
        used for (hyper)edge ids 
    node_col : (optional) int | str, default : 1
        column index (or name) in pandas.dataframe or numpy.ndarray, 
        used for node ids
    cell_weight_col : (optional) int | str, default = None
        column index (or name) in pandas.dataframe or numpy.ndarray used for
        referencing cell weights. For a dict of dicts references key in cell 
        property dicts.      
    cell_weights : (optional) Sequence[float,int] | int |  float , default : 1
        User specified cell_weights or default weight.
        Sequential values are only used if setsystem is a 
        dataframe or ndarray in which case the sequence must
        have the same length and order as these objects.
        Sequential values are ignored if cell_weight_col is given.
        If cell_weights is assigned a single value 
        then it will be used as default when no cell_weight_col 
        is given or if cell weight is missing from the cell_weight_col   
    cell_properties : (optional) Sequence[int | str] | Map[int | str , str], 
        default : None
        Indices or names of columns from set system to use as properties 
        or a dict assigning cell_property to incidence pairs of edges and nodes.
        Will update properties if setsystem is dict of dicts.
    misc_cell_properties : (optional) int | str, default="cell_properties" 
        Column index or name of dataframe corresponding to a column of variable
        length property dictionaries for the cell. Ignored for other setsystem
        types.
    aggregateby : (optional) str, dict optional, default : 'first'
        By default duplicate edge,node incidences will be dropped unless 
        specified with `aggregateby`.  
        See pandas.DataFrame.groupby() and pandas.DataFrame.agg() methods for 
        additional syntax and usage information.

    edge_properties : (optional) pd.DataFrame | dict, default : None
        Properties associated with edge ids.
        First column of dataframe or keys of dict link to object ids in 
        setsystem.
    node_properties : (optional) pd.DataFrame | dict, default : None
        Properties associated with node ids.
        First column of dataframe or keys of dict link to object ids in 
        setsystem.
    properties : (optional) pd.DataFrame | dict, default = None
        Concatenation/union of edge_properties and node_properties.
        By default the object id is used and should be the first column of
        the dataframe, or key in the dict. If there are nodes and edges
        with the same ids and different properties then the first column of the
        dataframe is binary indicator of 0 or edge_col_name and 1 or 
        node_col_name and the second column should reference object id. If a dict
        then nest the edge and node dictionaries with keys 0/edge_col_name 
        and 1/node_col_name. See notes for example.
    misc_properties : (optional) int | str, default = "properties"
        Column of property dataframes with dtype=dict. Intended for variable
        length property dictionaries for the objects.
    edge_weight_prop : (optional) str, default : 'weight', 
        Name of property in edge_properties to use for for weight.
    node_weight_prop : (optional) str, default : 'weight', 
        Name of property in node_properties to use for for weight.
    weight_prop : (optional) str, default : 'weight'
        Name of property in properties to use for 'weight' 
    default_edge_weight : (optional) int | float, default : 1
        Used when edge weight property is missing or undefined.
    default_node_weight : (optional) int | float, default : 1
        Used when node weight property is missing or undefined

    """

    @warn_nwhy
    def __init__(
        self,
        setsystem=None,
        name=None,
        static=False,
        weights=None,
        aggregateby="sum",
        use_nwhy=False,
        filepath=None,
        **kwargs,
    ):
        self.filepath = filepath
        if use_nwhy:
            static = True
        self.nwhy = False

        self.name = name or ""

        self._static = static

        if setsystem is None:
            self._edges = EntitySet(data=np.empty((0, 2), uid="Edges", dtype=int))
            self._nodes = EntitySet(data=np.empty((0, 1), uid="Nodes", dtype=int))
        else:
            try:
                kwargs.update(
                    properties=setsystem.properties,
                    misc_props_col=setsystem._misc_props_col,
                    level_col=setsystem.properties.index.names[0],
                    id_col=setsystem.properties.index.names[1],
                )
            except AttributeError:
                pass

            try:
                kwargs.update(
                    cell_properties=setsystem.cell_properties.reset_index(),
                    misc_cell_props_col=setsystem._misc_cell_props_col,
                )
            except AttributeError:
                pass

            E = EntitySet(
                entity=setsystem,
                weights=weights,
                aggregateby=aggregateby,
                static=static,
                uid="Edges",
                **kwargs
            )
            self._edges = E
            self._nodes = E.restrict_to_levels(
                [1], uid="Nodes", weights=False, aggregateby=None
            )

        self.state_dict = {}
        self.update_state()
        if self.filepath is not None:
            self.save_state(fpath=self.filepath)

    @property
    def edges(self):
        """
        Object associated with self._edges.

        Returns
        -------
        EntitySet
        """
        return self._edges

    @property
    def nodes(self):
        """
        Object associated with self._nodes.

        Returns
        -------
        EntitySet
        """
        return self._nodes

    @property
    def isstatic(self):
        """
        Checks whether nodes and edges are immutable

        Returns
        -------
        bool
        """
        return self._static

    @property
    def incidence_dict(self):
        """
        Dictionary keyed by edge uids with values the uids of nodes in each
        edge

        Returns
        -------
        dict

        """
        return self._edges.incidence_dict

    @property
    def shape(self):
        """
        (number of nodes, number of edges)

        Returns
        -------
        tuple

        """
        return len(self._nodes.elements), len(self._edges.elements)

    def __str__(self):
        """
        String representation of hypergraph

        Returns
        -------
        str

        """
        return f"Hypergraph({self.edges.elements},name={self.name})"

    def __repr__(self):
        """
        String representation of hypergraph

        Returns
        -------
        str

        """
        return f"Hypergraph({self.edges.elements},name={self.name})"

    def __len__(self):
        """
        Number of nodes

        Returns
        -------
        int

        """
        return len(self._nodes)

    def __iter__(self):
        """
        Iterate over the nodes of the hypergraph

        Returns
        -------
        dict_keyiterator

        """
        return iter(self.nodes)

    def __contains__(self, item):
        """
        Returns boolean indicating if item is in self.nodes

        Parameters
        ----------
        item : hashable or Entity

        """
        return item in self.nodes

    def __getitem__(self, node):
        """
        Returns the neighbors of node

        Parameters
        ----------
        node : Entity or hashable
            If hashable, then must be uid of node in hypergraph

        Returns
        -------
        neighbors(node) : iterator

        """
        return self.neighbors(node)

    # def get_id(self, uid, edges=False):
    #     """
    #     Return the internally assigned id associated with a label.

    #     Parameters
    #     ----------
    #     uid : string
    #         User provided name/id/label for hypergraph object
    #     edges : bool, optional
    #         Determines if uid is an edge or node name

    #     Returns
    #     -------
    #     : int
    #         internal id assigned at construction
    #     """
    #     column = self.edges._data_cols[int(not edges)]
    #     return self.edges.index(column, uid)[1]

    # def get_name(self, id, edges=False):
    #     """
    #     Return the user defined name/id/label associated to an
    #     internally assigned id.

    #     Parameters
    #     ----------
    #     id : int
    #         Internally assigned id
    #     edges : bool, optional
    #         Determines if id references an edge or node

    #     Returns
    #     -------
    #     str
    #         User provided name/id/label for hypergraph object
    #     """
    #     level = int(not edges)
    #     return self.edges.translate(level, id)

    def get_cell_properties(
        self, edge: str, node: str, prop_name: Optional[str] = None
    ) -> Any | dict[str, Any]:
        """Get cell properties on a specified edge and node

        Parameters
        ----------
        edge : str
            name of an edge
        node : str
            name of a node
        prop_name : str, optional
            name of a cell property; if None, all cell properties will be returned

        Returns
        -------
        any or dict of {str: any}
            cell property value if `prop_name` is provided, otherwise ``dict`` of all
            cell properties and values
        """
        if prop_name is None:
            return self.edges.get_cell_properties(edge, node)

        return self.edges.get_cell_property(edge, node, prop_name)

    @warn_nwhy
    def get_linegraph(self, s, edges=True, use_nwhy=False):
        """
        Creates an ::term::s-linegraph for the Hypergraph.
        If edges=True (default)then the edges will be the vertices of the line
        graph. Two vertices are connected by an s-line-graph edge if the
        corresponding hypergraph edges intersect in at least s hypergraph nodes.
        If edges=False, the hypergraph nodes will be the vertices of the line
        graph. Two vertices are connected if the nodes they correspond to share
        at least s incident hyper edges.

        Parameters
        ----------
        s : int
            The width of the connections.
        edges : bool, optional
            Determine if edges or nodes will be the vertices in the linegraph.
        use_nwhy : bool, optional
            Requests that nwhy be used to construct the linegraph. If NWHy is
            not available this is ignored.

        Returns
        -------
        nx.Graph
            A NetworkX graph.
        """
        d = self.state_dict
        key = "sedgelg" if edges else "snodelg"
        if s in d[key]:
            return d[key][s]

        if edges:
            A,Amap = self.edge_adjacency_matrix(s=s,index=True)
        else:
            A,Amap = self.adjacency_matrix(s=s,index=True)

        g = nx.from_scipy_sparse_matrix(A)
        g = nx.relabel_nodes(g,Amap)

        d[key][s] = g

        return g

    def set_state(self, **kwargs):
        """
        Allow state_dict updates from outside of class. Use with caution.

        Parameters
        ----------
        **kwargs
            key=value pairs to save in state dictionary
        """
        self.state_dict.update(kwargs)
        if self.filepath is not None:
            self.save_state(fpath=self.filepath)

    def update_state(self):
        """Populate state_dict with default values"""
        temprows, tempcols = self.edges.data.T
        tempdata = np.ones(len(temprows), dtype=int)
        self.state_dict["data"] = (temprows, tempcols, tempdata)
        self.state_dict["snodelg"] = {}
        self.state_dict["sedgelg"] = {}
        for sdkey in set(self.state_dict) - {"data", "snodelg", "sedgelg"}:
            self.state_dict.pop(sdkey)

    def save_state(self, fpath=None):
        """
        Save the hypergraph as an ordered pair: [state_dict,labels]
        The hypergraph can be recovered using the command:

            >>> H = hnx.Hypergraph.recover_from_state(fpath)

        Parameters
        ----------
        fpath : str, optional
        """
        fpath = fpath or self.filepath or "current_state.p"
        with open(fpath, "wb") as f:
            pickle.dump([self.state_dict, self.edges.labels], f)

    @classmethod
    @warn_nwhy
    def recover_from_state(cls, fpath="current_state.p", newfpath=None, use_nwhy=True):
        """
        Recover a static hypergraph pickled using save_state.

        Parameters
        ----------
        fpath : str
            Full path to pickle file containing state_dict and labels
            of hypergraph

        Returns
        -------
        H : Hypergraph
            static hypergraph with state dictionary prefilled
        """
        with open(fpath, "rb") as f:
            temp, labels = pickle.load(f)
        # need to save counts as well
        recovered_data = np.array(temp["data"])[[0, 1]].T
        recovered_counts = np.array(temp["data"])[
            [2]
        ]  # ammend this to store cell weights
        E = EntitySet(data=recovered_data, labels=labels)
        E.properties["counts"] = recovered_counts
        H = Hypergraph(E)
        H.state_dict.update(temp)
        if newfpath == "same":
            newfpath = fpath
        if newfpath is not None:
            H.filepath = newfpath
            H.save_state()
        return H

    # @classmethod
    # def add_nwhy(cls, h, fpath=None):
    #     """
    #     Add nwhy functionality to a hypergraph.

    #     Parameters
    #     ----------
    #     h : hnx.Hypergraph
    #     fpath : file path for storage of hypergraph state dictionary

    #     Returns
    #     -------
    #     hnx.Hypergraph
    #         Returns a copy of h with static set to true and nwhy set to True
    #         if it is available.

    #     """
    #     warnings.warn(NWHY_WARNING, DeprecationWarning, stacklevel=2)
    #     return h

    def edge_size_dist(self):
        """
        Returns the size for each edge

        Returns
        -------
        np.array

        """

        if "edge_size_dist" not in self.state_dict:
            dist = list(np.array(np.sum(self.incidence_matrix(), axis=0))[0])
            self.set_state(edge_size_dist=dist)

        return self.state_dict["edge_size_dist"]

    # @warn_nwhy
    # def convert_to_static(
    #     self,
    #     name=None,
    #     use_nwhy=False,
    #     filepath=None,
    # ):
    #     """
    #     Returns new static hypergraph with the same dictionary as original
    #     hypergraph

    #     Parameters
    #     ----------
    #     name : None, optional
    #         Name
    #     use_nwhy : bool, optional, default : False
    #         Description
    #     filepath : None, optional, default : False
    #         Description

    #     Returned
    #     ------------------
    #     hnx.Hypergraph
    #         Will have attribute static = True

    #     Note
    #     ----
    #     Static hypergraphs store the user defined node and edge names in
    #     a dictionary of labeled lists. The order of the lists provides an
    #     index, which the hypergraph uses in place of the node and edge names
    #     for faster processing.

    #     """
    #     if self.edges.isstatic and self.nodes.isstatic:
    #         self._static = True

    #     if self.isstatic:
    #         return self

    #     E = EntitySet(self.edges, static=True)
    #     return Hypergraph(E, filepath=filepath, name=name, static=True)

    # def remove_static(self, name=None):
    #     """
    #     Returns dynamic hypergraph

    #     Parameters
    #     ----------
    #     name : None, optional
    #         User defined namae of hypergraph

    #     Returns
    #     -------
    #     hnx.Hypergraph
    #         A new hypergraph with the same dictionary as self but allowing
    #         dynamic changes to nodes and edges.
    #         If hypergraph is not static, returns self.
    #     """
    #     if not self.isstatic:
    #         return self

    #     return Hypergraph(self.edges, name=name)

    # def translate(self, idx, edges=False):
    #     """
    #     Returns the translation of numeric values associated with hypergraph.
    #     Only needed if exposing the static identifiers assigned by the class.
    #     If not static then the idx is returned.

    #     Parameters
    #     ----------
    #     idx : int
    #         class assigned integer for internal manipulation of Hypergraph data
    #     edges : bool, optional, default: True
    #         If True then translates from edge index. Otherwise will translate
    #         from node index, default=False

    #     Returns
    #     -------
    #      : int or string
    #         User assigned identifier corresponding to idx
    #     """
    #     return self.get_name(idx, edges=edges)

    # def s_degree(self, node, s=1):  # deprecate this to degree
    #     """
    #     Same as `degree`

    #     Parameters
    #     ----------
    #     node : Entity or hashable
    #         If hashable, then must be uid of node in hypergraph

    #     s : positive integer, optional, default: 1

    #     Returns
    #     -------
    #     s_degree : int
    #         The degree of a node in the subgraph induced by edges
    #         of size s

    #     Note
    #     ----
    #     The :term:`s-degree` of a node is the number of edges of size
    #     at least s that contain the node.

    #     """
    #     msg = (
    #         "s-degree is deprecated and will be removed in"
    #         " release 1.0.0. Use degree(node,s=int) instead."
    #     )

    #     warnings.warn(msg, DeprecationWarning)
    #     return self.degree(node, s)

    def degree(self, node, s=1, max_size=None):
        """
        The number of edges of size s that contain node.

        Parameters
        ----------
        node : hashable
            identifier for the node.
        s : positive integer, optional, default: 1
            smallest size of edge to consider in degree
        max_size : positive integer or None, optional, default: None
            largest size of edge to consider in degree

        Returns
        -------
         : int

        """

        memberships = set()
        for edge in self.nodes.memberships[node]:
            size = len(self.edges[edge])
            if size >= s and (max_size is None or size <= max_size):
                memberships.add(edge)

        return len(memberships)

    def size(self, edge, nodeset=None):
        """
        The number of nodes in nodeset that belong to edge.
        If nodeset is None then returns the size of edge

        Parameters
        ----------
        edge : hashable
            The uid of an edge in the hypergraph

        Returns
        -------
        size : int

        """
        if nodeset is not None:
            return len(set(nodeset).intersection(set(self.edges[edge])))

        return len(self.edges[edge])

    def number_of_nodes(self, nodeset=None):
        """
        The number of nodes in nodeset belonging to hypergraph.

        Parameters
        ----------
        nodeset : an interable of Entities, optional, default: None
            If None, then return the number of nodes in hypergraph.

        Returns
        -------
        number_of_nodes : int

        """
        if nodeset is not None:
            return len([n for n in self.nodes if n in nodeset])

        return len(self.nodes)

    def number_of_edges(self, edgeset=None):
        """
        The number of edges in edgeset belonging to hypergraph.

        Parameters
        ----------
        edgeset : an iterable of Entities, optional, default: None
            If None, then return the number of edges in hypergraph.

        Returns
        -------
        number_of_edges : int
        """
        if edgeset:
            return len([e for e in self.edges if e in edgeset])

        return len(self.edges)

    def order(self):
        """
        The number of nodes in hypergraph.

        Returns
        -------
        order : int
        """
        return len(self.nodes)

    def dim(self, edge):
        """
        Same as size(edge)-1.
        """
        return self.size(edge) - 1

    def neighbors(self, node, s=1):
        """
        The nodes in hypergraph which share s edge(s) with node.

        Parameters
        ----------
        node : hashable or Entity
            uid for a node in hypergraph or the node Entity

        s : int, list, optional, default : 1
            Minimum number of edges shared by neighbors with node.

        Returns
        -------
         : list
            List of neighbors

        """
        if node not in self.nodes:
            print(f"Node is not in hypergraph {self.name}.")
            return None
        g = self.get_linegraph(s=s, edges=False)
        return g.neighbors(node)

    def edge_neighbors(self, edge, s=1):
        """
        The edges in hypergraph which share s nodes(s) with edge.

        Parameters
        ----------
        edge : hashable or Entity
            uid for a edge in hypergraph or the edge Entity

        s : int, list, optional, default : 1
            Minimum number of nodes shared by neighbors edge node.

        Returns
        -------
         : list
            List of edge neighbors

        """
        if edge not in self.edges:
            print(f"Edge is not in hypergraph {self.name}.")
            return None

        g = self.get_linegraph(s=s, edges=True)
        return g.neighbors(edge)


    def remove_node(self, node, update_state=True):
        """
        Removes node from edges and deletes reference in hypergraph nodes

        Parameters
        ----------
        node : hashable or Entity
            a node in hypergraph

        Returns
        -------
        hypergraph : Hypergraph

        """

        if node in self._nodes:
            for edge in self._edges.memberships[node]:
                if node in self._edges[edge]:
                    self._edges.remove(node)
            self._nodes.remove(node)

            if update_state:
                self.update_state()

        return self

    def remove_nodes(self, node_set):
        """
        Removes nodes from edges and deletes references in hypergraph nodes

        Parameters
        ----------
        node_set : an iterable of hashables or Entities
            Nodes in hypergraph

        Returns
        -------
        hypergraph : Hypergraph

        """
        for node in node_set:
            self.remove_node(node, update_state=False)
        self.update_state()
        return self

    def _add_nodes_from(self, nodes):
        """
        Private helper method instantiates new nodes when edges added to
        hypergraph.

        Parameters
        ----------
        nodes : iterable of hashables or Entities

        """
        self._nodes.add(nodes)

    def add_edge(self, edge, update_state=True):
        """

        Adds a single edge to hypergraph.

        Parameters
        ----------
        edge : hashable or Entity
            If hashable the edge returned will be empty.

        Returns
        -------
        hypergraph : Hypergraph

        Notes
        -----
        When adding an edge to a hypergraph children must be removed
        so that nodes do not have elements.
        Each node (element of edge) must be instantiated as a node,
        making sure its uid isn't already present in the self.
        If an added edge contains nodes that cannot be added to hypergraph
        then an error will be raised.

        """
        # This piece of code is to allow a user to pass in a dictionary
        # Of the format {'New_edge': ['Node1', 'Node2']}.
        # TODO: type check to correctly handle other valid input types
        cols = list(self._edges.labels.keys())
        edge = {cols[0]: list(edge.keys())[0], cols[1]: list(edge.values())[0]}

        key = edge[cols[0]]

        if key in self._edges.elements:
            warnings.warn("Cannot add edge. Edge already in hypergraph")
        elif key in self._nodes.elements:
            warnings.warn("Cannot add edge. Edge is already a Node")
        if len(edge) > 0:
            # TODO: this isn't right
            self._nodes.add(edge)
            self._edges.add(edge)

        if update_state:
            self.update_state()

    def add_edges_from(self, edge_set):
        """
        Add edges to hypergraph.

        Parameters
        ----------
        edge_set : iterable of hashables or Entities
            For hashables the edges returned will be empty.

        Returns
        -------
        hypergraph : Hypergraph

        """
        for edge in edge_set:
            self.add_edge(edge, update_state=False)

        self.update_state()
        return self

    def add_node_to_edge(self, node, edge, update_state=True):
        """

        Adds node to an edge in hypergraph edges

        Parameters
        ----------
        node: hashable or Entity
            If Entity, only uid and properties will be used.
            If uid is already in nodes then the known node will
            be used

        edge: uid of edge or edge, must belong to self.edges

        Returns
        -------
        hypergraph : Hypergraph

        """
        if edge in self._edges:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", message="Cannot add edge. Edge already in hypergraph"
                )
                self.add_edge({edge: [node]}, update_state)

        return self

    def remove_edge(self, edge, update_state=True):
        """
        Removes a single edge from hypergraph.

        Parameters
        ----------
        edge : hashable or Entity

        Returns
        -------
        hypergraph : Hypergraph

        Notes
        -----

        Deletes reference to edge from all of its nodes.
        If any of its nodes do not belong to any other edges
        the node is dropped from self.

        """
        if edge in self.edges:
            for node in self.edges[edge]:
                if len(self.edges.memberships[node]) == 1:
                    self.remove_node(node)
            self._edges.remove(edge)

        if update_state:
            self.update_state()
        return self

    def remove_edges(self, edge_set):
        """
        Removes edges from hypergraph.

        Parameters
        ----------
        edge_set : iterable of hashables or Entities

        Returns
        -------
        hypergraph : Hypergraph

        """
        for edge in edge_set:
            self.remove_edge(edge, update_state=False)

        self.update_state()
        return self

    def incidence_matrix(self, weights=False, index=False):
        """
        An incidence matrix for the hypergraph indexed by nodes x edges.

        Parameters
        ----------
        weights : bool, default=False
            If False all nonzero entries are 1.
            If True and self.static all nonzero entries are filled by
            self.edges.cell_weights dictionary values.

        index : boolean, optional, default False
            If True return will include a dictionary of node uid : row number
            and edge uid : column number

        Returns
        -------
        incidence_matrix : scipy.sparse.csr.csr_matrix or np.ndarray

        row dictionary : dict
            Dictionary identifying rows with nodes

        column dictionary : dict
            Dictionary identifying columns with edges

        """
        sdkey = "incidence_matrix"
        if weights:
            sdkey = "weighted_" + sdkey

        if sdkey not in self.state_dict:
            self.state_dict[sdkey] = self.edges.incidence_matrix(weights=weights)

        if index:
            edgecol, nodecol = self.edges._data_cols
            rdict = dict(enumerate(self.edges.labels[nodecol]))
            cdict = dict(enumerate(self.edges.labels[edgecol]))

            return self.state_dict[sdkey], rdict, cdict

        return self.state_dict[sdkey]

    @staticmethod
    def _incidence_to_adjacency(M, s=1, weights=False):
        """
        Helper method to obtain adjacency matrix from
        boolean incidence matrix for s-metrics.
        Self loops are not supported.
        The adjacency matrix will define an s-linegraph.

        Parameters
        ----------
        M : scipy.sparse.csr.csr_matrix
            incidence matrix of 0's and 1's

        s : int, optional, default: 1

        # weights : bool, dict optional, default=True
        #     If False all nonzero entries are 1.
        #     Otherwise, weights will be as in product.

        Returns
        -------
        a matrix : scipy.sparse.csr.csr_matrix

        """
        M = csr_matrix(M)
        weights = False  # currently weighting is not supported

        if weights is False:
            A = M.dot(M.transpose())
            A.setdiag(0)
            A = (A >= s) * 1
        return A

    def adjacency_matrix(self, index=False, s=1):  # , weights=False):
        """
        The sparse weighted :term:`s-adjacency matrix`

        Parameters
        ----------
        s : int, optional, default: 1

        index: boolean, optional, default: False
            if True, will return a rowdict of row to node uid

        weights: bool, default=True
            If False all nonzero entries are 1.
            If True adjacency matrix will depend on weighted incidence matrix,

        Returns
        -------
        adjacency_matrix : scipy.sparse.csr.csr_matrix

        row dictionary : dict

        """
        weights = False  # Currently default weights are not supported.
        M = self.incidence_matrix(index=index, weights=weights)

        if index:
            return Hypergraph._incidence_to_adjacency(M[0], s=s, weights=weights), M[1]

        return Hypergraph._incidence_to_adjacency(M, s=s, weights=weights)

    def edge_adjacency_matrix(self, index=False, s=1, weights=False):
        """
        The weighted :term:`s-adjacency matrix` for the dual hypergraph.

        Parameters
        ----------
        s : int, optional, default: 1

        index: boolean, optional, default: False
            if True, will return a coldict of column to edge uid

        sparse: boolean, optional, default: True

        weighted: boolean, optional, default: True

        Returns
        -------
        edge_adjacency_matrix : scipy.sparse.csr.csr_matrix or numpy.ndarray

        column dictionary : dict

        Notes
        -----
        This is also the adjacency matrix for the line graph.
        Two edges are s-adjacent if they share at least s nodes.
        If index=True, returns a dictionary column_index:edge_uid

        """
        weights = False  # Currently default weights are not supported

        M = self.incidence_matrix(index=index, weights=weights)
        if index:
            return (
                Hypergraph._incidence_to_adjacency(
                    M[0].transpose(), s=s, weights=weights
                ),
                M[2],
            )

        return Hypergraph._incidence_to_adjacency(M.transpose(), s=s, weights=weights)

    def auxiliary_matrix(self, s=1, index=False):
        """
        The unweighted :term:`s-auxiliary matrix` for hypergraph

        Parameters
        ----------
        s : int
        index : bool, optional, default: False
            return a dictionary of labels for the rows of the matrix


        Returns
        -------
        auxiliary_matrix : scipy.sparse.csr.csr_matrix or numpy.ndarray
            Will return the same type of matrix as self.arr

        Notes
        -----
        Creates subgraph by restricting to edges of cardinality at least s.
        Returns the unweighted s-edge adjacency matrix for the subgraph.

        """

        edges = [e for e in self.edges if len(self.edges[e]) >= s]
        H = self.restrict_to_edges(edges)
        return H.edge_adjacency_matrix(s=s, index=index, weights=False)

    def bipartite(self):
        """
        Constructs the networkX bipartite graph associated to hypergraph.

        Returns
        -------
        bipartite : nx.Graph()

        Notes
        -----
        Creates a bipartite networkx graph from hypergraph.
        The nodes and (hyper)edges of hypergraph become the nodes of bipartite
        graph. For every (hyper)edge e in the hypergraph and node n in e there
        is an edge (n,e) in the graph.

        """
        B = nx.Graph()
        B.add_nodes_from(self.edges, bipartite=1)
        B.add_nodes_from(self.nodes, bipartite=0)
        B.add_edges_from([(v, e) for e in self.edges for v in self.edges[e]])
        return B

    def dual(self, name=None):
        """
        Constructs a new hypergraph with roles of edges and nodes of hypergraph
        reversed.

        Parameters
        ----------
        name : hashable

        Returns
        -------
        dual : hypergraph
        """
        E = self.edges.restrict_to_levels((1, 0))
        return Hypergraph(E, name=name)

    def _collapse_nwhy(self, edges, rec):
        """
        Helper method for collapsing nodes and edges when hypergraph
        is static and using nwhy

        Parameters
        ----------
        edges : bool
            Collapse the edges if True, otherwise the nodes
        rec : bool
            return the equivalence classes
        """

        warnings.warn(NWHY_WARNING, DeprecationWarning, stacklevel=2)
        return None

    def collapse_edges(
        self,
        name=None,
        use_reps=None,
        return_counts=None,
        return_equivalence_classes=False,
    ):
        """
        Constructs a new hypergraph gotten by identifying edges containing the
        same nodes

        Parameters
        ----------
        name : hashable, optional, default: None

        return_equivalence_classes: boolean, optional, default: False
            Returns a dictionary of edge equivalence classes keyed by frozen
            sets of nodes

        Returns
        -------
        new hypergraph : Hypergraph
            Equivalent edges are collapsed to a single edge named by a
            representative of the equivalent edges followed by a colon and the
            number of edges it represents.

        equivalence_classes : dict
            A dictionary keyed by representative edge names with values equal
            to the edges in its equivalence class

        Notes
        -----
        Two edges are identified if their respective elements are the same.
        Using this as an equivalence relation, the uids of the edges are
        partitioned into equivalence classes.

        A single edge from the collapsed edges followed by a colon and the
        number of elements in its equivalence class as uid for the new edge


        """
        if use_reps is not None or return_counts is not None:
            msg = """
            use_reps ane return_counts are no longer supported keyword
            arguments and will throw an error in the next release.
            collapsed hypergraph automatically names collapsed objects by a
            string "rep:count"
            """
            warnings.warn(msg, DeprecationWarning)

        temp = self.edges.collapse_identical_elements(
            return_equivalence_classes=return_equivalence_classes
        )

        if return_equivalence_classes:
            return Hypergraph(temp[0], name), temp[1]

        return Hypergraph(temp, name)

    def collapse_nodes(
        self,
        name=None,
        use_reps=True,
        return_counts=True,
        return_equivalence_classes=False,
    ):
        """
        Constructs a new hypergraph gotten by identifying nodes contained by
        the same edges

        Parameters
        ----------
        name: str, optional, default: None

        return_equivalence_classes: boolean, optional, default: False
            Returns a dictionary of node equivalence classes keyed by frozen
            sets of edges

        use_reps : boolean, optional, default: False - Deprecated, this no
            longer works and will be removed. Choose a single element from the
            collapsed nodes as uid for the new node, otherwise uses a frozen
            set of the uids of nodes in the equivalence class

        return_counts: boolean, - Deprecated, this no longer works and will be
            removed if use_reps is True the new nodes have uids given by a
            tuple of the rep and the count

        Returns
        -------
        new hypergraph : Hypergraph

        Notes
        -----
        Two nodes are identified if their respective memberships are the same.
        Using this as an equivalence relation, the uids of the nodes are
        partitioned into equivalence classes. A single member of the
        equivalence class is chosen to represent the class followed by the
        number of members of the class.

        Example
        -------

            >>> h = Hypergraph(EntitySet('example',elements=[Entity('E1', /
                                        ['a','b']),Entity('E2',['a','b'])]))
            >>> h.incidence_dict
            {'E1': {'a', 'b'}, 'E2': {'a', 'b'}}
            >>> h.collapse_nodes().incidence_dict
            {'E1': {frozenset({'a', 'b'})}, 'E2': {frozenset({'a', 'b'})}}
            ### Fix this
            >>> h.collapse_nodes(use_reps=True).incidence_dict
            {'E1': {('a', 2)}, 'E2': {('a', 2)}}

        """
        if use_reps is not None or return_counts is not None:
            msg = """
            use_reps and return_counts are no longer supported keyword arguments and will throw
            an error in the next release.
            collapsed hypergraph automatically names collapsed objects by a string "rep:count"
            """
            warnings.warn(msg, DeprecationWarning)

        temp = self.dual().edges.collapse_identical_elements(
            return_equivalence_classes=return_equivalence_classes
        )

        if return_equivalence_classes:
            return Hypergraph(temp[0], name).dual(), temp[1]

        return Hypergraph(temp, name).dual()

    def collapse_nodes_and_edges(
        self,
        name=None,
        use_reps=True,
        return_counts=True,
        return_equivalence_classes=False,
    ):
        """
        Returns a new hypergraph by collapsing nodes and edges.

        Parameters
        ----------

        name: str, optional, default: None

        use_reps: boolean, optional, default: False
            Choose a single element from the collapsed elements as a
            representative

        return_counts: boolean, optional, default: True
            if use_reps is True the new elements are keyed by a tuple of the
            rep and the count

        return_equivalence_classes: boolean, optional, default: False
            Returns a dictionary of edge equivalence classes keyed by frozen
            sets of nodes

        Returns
        -------
        new hypergraph : Hypergraph

        Notes
        -----
        Collapses the Nodes and Edges EntitySets. Two nodes(edges) are
        duplicates if their respective memberships(elements) are the same.
        Using this as an equivalence relation, the uids of the nodes(edges)
        are partitioned into equivalence classes. A single member of the
        equivalence class is chosen to represent the class followed by the
        number of members of the class.

        Example
        -------

            >>> h = Hypergraph(EntitySet('example',elements=[Entity('E1', /
                                           ['a','b']),Entity('E2',['a','b'])]))
            >>> h.incidence_dict
            {'E1': {'a', 'b'}, 'E2': {'a', 'b'}}
            >>> h.collapse_nodes_and_edges().incidence_dict   ### Fix this
            {('E1', 2): {('a', 2)}}

        """
        if use_reps is not None or return_counts is not None:
            msg = """
            use_reps ane return_counts are no longer supported keyword
            arguments and will throw an error in the next release.
            collapsed hypergraph automatically names collapsed objects by a
            string "rep:count"
            """
            warnings.warn(msg, DeprecationWarning)

        if return_equivalence_classes:
            temp, neq = self.collapse_nodes(
                name="temp", return_equivalence_classes=True
            )
            ntemp, eeq = temp.collapse_edges(name=name, return_equivalence_classes=True)
            return ntemp, neq, eeq

        temp = self.collapse_nodes(name="temp")
        return temp.collapse_edges(name=name)

    def restrict_to_edges(self, edgeset, name=None):
        """
        Constructs a hypergraph using a subset of the edges in hypergraph

        Parameters
        ----------
        edgeset: iterable of hashables or Entities
            A subset of elements of the hypergraph edges

        name: str, optional

        Returns
        -------
        new hypergraph : Hypergraph
        """

        indices = self.edges.indices(self.edges._data_cols[0], list(edgeset))
        setsystem = self.edges.restrict_to(sorted(indices))
        return Hypergraph(setsystem, name=name)

    def restrict_to_nodes(self, nodeset, name=None):
        """
        Constructs a new hypergraph by restricting the edges in the hypergraph
        to the nodes referenced by nodeset.

        Parameters
        ----------
        nodeset: iterable of hashables
            References a subset of elements of self.nodes

        name: string, optional, default: None

        Returns
        -------
        new hypergraph : Hypergraph
        """
        indices = self.edges.indices(self.edges._data_cols[1], list(nodeset))
        setsystem = self.edges.restrict_to_indices(sorted(indices), level=1)
        return Hypergraph(setsystem, name=name)

    def toplexes(self, name=None, collapse=False, use_reps=False, return_counts=True):
        """
        Returns a :term:`simple hypergraph` corresponding to self.

        Warning
        -------
        Collapsing is no longer supported inside the toplexes method. Instead
        generate a new collapsed hypergraph and compute the toplexes of the
        new hypergraph.

        Parameters
        ----------
        name: str, optional, default: None

        # collapse: boolean, optional, default: False
        #     Should the hypergraph be collapsed? This would preserve a link
        #     between duplicate maximal sets. If False then only one of these
        #     sets will be used and uniqueness will be up to sets of equal
        #     size.

        # use_reps: boolean, optional, default: False
        #     If collapse=True then each toplex will be named by a
        #     representative of the set of equivalent edges, default is False
        #     (see collapse_edges).

        return_counts: boolean, optional, default: True
            # If collapse=True then each toplex will be named by a tuple of
            # the representative of the set of equivalent edges and their count

        """
        # TODO: There is a better way to do this....need to refactor
        if collapse:
            if len(self.edges) > 20:  # TODO: Determine how big is too big.
                msg = """
                Collapsing a hypergraph can take a long time. It may be preferable to
                collapse the graph first and pickle it then apply the toplex method
                separately.
                """
                warnings.warn(msg)
            temp = self.collapse_edges()
        else:
            temp = self

        if collapse:
            msg = """
            collapse, return_counts, and use_reps are no longer supported
            keyword arguments and will throw an error in the next release.
            """
            warnings.warn(msg, DeprecationWarning)

        thdict = {}
        for e in temp.edges:
            thdict[e] = temp.edges[e]

        tops = []
        for e in temp.edges:
            flag = True
            old_tops = list(tops)
            for top in old_tops:
                if set(thdict[e]).issubset(thdict[top]):
                    flag = False
                    break

                if set(thdict[top]).issubset(thdict[e]):
                    tops.remove(top)
            if flag:
                tops += [e]
        return self.restrict_to_edges(tops, name=name)

    def is_connected(self, s=1, edges=False):
        """
        Determines if hypergraph is :term:`s-connected <s-connected,
        s-node-connected>`.

        Parameters
        ----------
        s: int, optional, default: 1

        edges: boolean, optional, default: False
            If True, will determine if s-edge-connected.
            For s=1 s-edge-connected is the same as s-connected.

        Returns
        -------
        is_connected : boolean

        Notes
        -----

        A hypergraph is s node connected if for any two nodes v0,vn
        there exists a sequence of nodes v0,v1,v2,...,v(n-1),vn
        such that every consecutive pair of nodes v(i),v(i+1)
        share at least s edges.

        A hypergraph is s edge connected if for any two edges e0,en
        there exists a sequence of edges e0,e1,e2,...,e(n-1),en
        such that every consecutive pair of edges e(i),e(i+1)
        share at least s nodes.

        """

        g = self.get_linegraph(s=s, edges=edges)
        return nx.is_connected(g)

    def singletons(self):
        """
        Returns a list of singleton edges. A singleton edge is an edge of
        size 1 with a node of degree 1.

        Returns
        -------
        singles : list
            A list of edge uids.
        """

        M, _, cdict = self.incidence_matrix(index=True)
        # which axis has fewest members? if 1 then columns
        idx = np.argmax(M.shape)
        # we add down the row index if there are fewer columns
        cols = M.sum(idx)
        singles = []
        # index along opposite axis
        for c in range(cols.shape[(idx + 1) % 2]):
            if cols[idx * c, c * ((idx + 1) % 2)] == 1:
                # then see if the singleton entry in that column is also
                # singleton in its row find the entry
                if idx == 0:
                    r = np.argmax(M.getcol(c))
                    # and get its sum
                    s = np.sum(M.getrow(r))
                    # if this is also 1 then the entry in r,c represents a
                    # singleton so we want to change that entry to 0 and
                    # remove the row. this means we want to remove the
                    # edge corresponding to c
                    if s == 1:
                        singles.append(cdict[c])
                else:  # switch the role of r and c
                    r = np.argmax(M.getrow(c))
                    s = np.sum(M.getcol(r))
                    if s == 1:
                        singles.append(cdict[r])
        return singles

    def remove_singletons(self, name=None):
        """
        Constructs clone of hypergraph with singleton edges removed.

        Parameters
        ----------
        name: str, optional, default: None

        Returns
        -------
        new hypergraph : Hypergraph

        """
        singletons = self.singletons()
        E = [e for e in self.edges if e not in singletons]
        return self.restrict_to_edges(E, name=name)

    def s_connected_components(self, s=1, edges=True, return_singletons=False):
        """
        Returns a generator for the :term:`s-edge-connected components
        <s-edge-connected component>`
        or the :term:`s-node-connected components <s-connected component,
        s-node-connected component>` of the hypergraph.

        Parameters
        ----------
        s : int, optional, default: 1

        edges : boolean, optional, default: True
            If True will return edge components, if False will return node
            components
        return_singletons : bool, optional, default : False

        Notes
        -----
        If edges=True, this method returns the s-edge-connected components as
        lists of lists of edge uids.
        An s-edge-component has the property that for any two edges e1 and e2
        there is a sequence of edges starting with e1 and ending with e2
        such that pairwise adjacent edges in the sequence intersect in at least
        s nodes. If s=1 these are the path components of the hypergraph.

        If edges=False this method returns s-node-connected components.
        A list of sets of uids of the nodes which are s-walk connected.
        Two nodes v1 and v2 are s-walk-connected if there is a
        sequence of nodes starting with v1 and ending with v2 such that
        pairwise adjacent nodes in the sequence share s edges. If s=1 these
        are the path components of the hypergraph.

        Example
        -------
            >>> S = {'A':{1,2,3},'B':{2,3,4},'C':{5,6},'D':{6}}
            >>> H = Hypergraph(S)

            >>> list(H.s_components(edges=True))
            [{'C', 'D'}, {'A', 'B'}]
            >>> list(H.s_components(edges=False))
            [{1, 2, 3, 4}, {5, 6}]

        Yields
        ------
        s_connected_components : iterator
            Iterator returns sets of uids of the edges (or nodes) in the
            s-edge(node) components of hypergraph.

        """
        g = self.get_linegraph(s, edges=edges)
        for c in nx.connected_components(g):
            if not return_singletons and len(c) == 1:
                continue
            yield c

    def s_component_subgraphs(self, s=1, edges=True, return_singletons=False):
        """

        Returns a generator for the induced subgraphs of s_connected
        components. Removes singletons unless return_singletons is set to True.
        Computed using s-linegraph generated either by the hypergraph
        (edges=True) or its dual (edges = False)

        Parameters
        ----------
        s : int, optional, default: 1

        edges : boolean, optional, edges=False
            Determines if edge or node components are desired. Returns
            subgraphs equal to the hypergraph restricted to each set of
            nodes(edges) in the s-connected components or s-edge-connected
            components
        return_singletons : bool, optional

        Yields
        ------
        s_component_subgraphs : iterator
            Iterator returns subgraphs generated by the edges (or nodes) in the
            s-edge(node) components of hypergraph.

        """
        for idx, c in enumerate(
            self.s_components(s=s, edges=edges, return_singletons=return_singletons)
        ):
            if edges:
                yield self.restrict_to_edges(c, name=f"{self.name}:{idx}")
            else:
                yield self.restrict_to_nodes(c, name=f"{self.name}:{idx}")

    def s_components(self, s=1, edges=True, return_singletons=True):
        """
        Same as s_connected_components

        See Also
        --------
        s_connected_components
        """
        return self.s_connected_components(
            s=s, edges=edges, return_singletons=return_singletons
        )

    def connected_components(self, edges=False):
        """
        Same as :meth:`s_connected_components` with s=1, but nodes are returned
        by default. Return iterator.

        See Also
        --------
        s_connected_components
        """
        return self.s_connected_components(edges=edges, return_singletons=True)

    def connected_component_subgraphs(self, return_singletons=True):
        """
        Same as :meth:`s_component_subgraphs` with s=1. Returns iterator

        See Also
        --------
        s_component_subgraphs
        """
        return self.s_component_subgraphs(return_singletons=return_singletons)

    def components(self, edges=False):
        """
        Same as :meth:`s_connected_components` with s=1, but nodes are returned
        by default. Return iterator.

        See Also
        --------
        s_connected_components
        """
        return self.s_connected_components(s=1, edges=edges)

    def component_subgraphs(self, return_singletons=False):
        """
        Same as :meth:`s_components_subgraphs` with s=1. Returns iterator.

        See Also
        --------
        s_component_subgraphs
        """
        return self.s_component_subgraphs(return_singletons=return_singletons)

    def node_diameters(self, s=1):
        """
        Returns the node diameters of the connected components in hypergraph.

        Parameters
        ----------
        list of the diameters of the s-components and
        list of the s-component nodes
        """
        A, coldict = self.adjacency_matrix(s=s, index=True)
        G = nx.from_scipy_sparse_matrix(A)
        diams = []
        comps = []
        for c in nx.connected_components(G):
            diamc = nx.diameter(G.subgraph(c))
            temp = set()
            for e in c:
                temp.add(coldict[e])
            comps.append(temp)
            diams.append(diamc)
        loc = np.argmax(diams)
        return diams[loc], diams, comps

    def edge_diameters(self, s=1):
        """
        Returns the edge diameters of the s_edge_connected component subgraphs
        in hypergraph.

        Parameters
        ----------
        s : int, optional, default: 1

        Returns
        -------
        maximum diameter : int

        list of diameters : list
            List of edge_diameters for s-edge component subgraphs in hypergraph

        list of component : list
            List of the edge uids in the s-edge component subgraphs.

        """
        A, coldict = self.edge_adjacency_matrix(s=s, index=True)
        G = nx.from_scipy_sparse_matrix(A)
        diams = []
        comps = []
        for c in nx.connected_components(G):
            diamc = nx.diameter(G.subgraph(c))
            temp = set()
            for e in c:
                temp.add(coldict[e])
            comps.append(temp)
            diams.append(diamc)
        loc = np.argmax(diams)
        return diams[loc], diams, comps

    def diameter(self, s=1):
        """
        Returns the length of the longest shortest s-walk between nodes in
        hypergraph

        Parameters
        ----------
        s : int, optional, default: 1

        Returns
        -------
        diameter : int

        Raises
        ------
        HyperNetXError
            If hypergraph is not s-edge-connected

        Notes
        -----
        Two nodes are s-adjacent if they share s edges.
        Two nodes v_start and v_end are s-walk connected if there is a
        sequence of nodes v_start, v_1, v_2, ... v_n-1, v_end such that
        consecutive nodes are s-adjacent. If the graph is not connected,
        an error will be raised.

        """
        A = self.adjacency_matrix(s=s)
        G = nx.from_scipy_sparse_matrix(A)
        if nx.is_connected(G):
            return nx.diameter(G)

        raise HyperNetXError(f"Hypergraph is not s-connected. s={s}")

    def edge_diameter(self, s=1):
        """
        Returns the length of the longest shortest s-walk between edges in
        hypergraph

        Parameters
        ----------
        s : int, optional, default: 1

        Return
        ------
        edge_diameter : int

        Raises
        ------
        HyperNetXError
            If hypergraph is not s-edge-connected

        Notes
        -----
        Two edges are s-adjacent if they share s nodes.
        Two nodes e_start and e_end are s-walk connected if there is a
        sequence of edges e_start, e_1, e_2, ... e_n-1, e_end such that
        consecutive edges are s-adjacent. If the graph is not connected, an
        error will be raised.

        """
        A = self.edge_adjacency_matrix(s=s)
        G = nx.from_scipy_sparse_matrix(A)
        if nx.is_connected(G):
            return nx.diameter(G)

        raise HyperNetXError(f"Hypergraph is not s-connected. s={s}")

    def distance(self, source, target, s=1):
        """
        Returns the shortest s-walk distance between two nodes in the
        hypergraph.

        Parameters
        ----------
        source : node.uid or node
            a node in the hypergraph

        target : node.uid or node
            a node in the hypergraph

        s : positive integer
            the number of edges

        Returns
        -------
        s-walk distance : int

        See Also
        --------
        edge_distance

        Notes
        -----
        The s-distance is the shortest s-walk length between the nodes.
        An s-walk between nodes is a sequence of nodes that pairwise share
        at least s edges. The length of the shortest s-walk is 1 less than
        the number of nodes in the path sequence.

        Uses the networkx shortest_path_length method on the graph
        generated by the s-adjacency matrix.

        """
        g = self.get_linegraph(s=s, edges=False)
        try:
            dist = nx.shortest_path_length(g, source, target)
        except nx.NetworkXNoPath:
            warnings.warn(f"No {s}-path between {source} and {target}")
            dist = np.inf

        return dist

    def edge_distance(self, source, target, s=1):
        """XX TODO: still need to return path and translate into user defined
        nodes and edges Returns the shortest s-walk distance between two edges
        in the hypergraph.

        Parameters
        ----------
        source : edge.uid or edge
            an edge in the hypergraph

        target : edge.uid or edge
            an edge in the hypergraph

        s : positive integer
            the number of intersections between pairwise consecutive edges

        TODO: add edge weights
        weight : None or string, optional, default: None
            if None then all edges have weight 1. If string then edge attribute
            string is used if available.


        Returns
        -------
        s- walk distance : the shortest s-walk edge distance
            A shortest s-walk is computed as a sequence of edges,
            the s-walk distance is the number of edges in the sequence
            minus 1. If no such path exists returns np.inf.

        See Also
        --------
        distance

        Notes
        -----
            The s-distance is the shortest s-walk length between the edges.
            An s-walk between edges is a sequence of edges such that
            consecutive pairwise edges intersect in at least s nodes. The
            length of the shortest s-walk is 1 less than the number of edges
            in the path sequence.

            Uses the networkx shortest_path_length method on the graph
            generated by the s-edge_adjacency matrix.

        """
        g = self.get_linegraph(s=s, edges=True)
        try:
            edge_dist = nx.shortest_path_length(g, source, target)
        except nx.NetworkXNoPath:
            warnings.warn(f"No {s}-path between {source} and {target}")
            edge_dist = np.inf

        return edge_dist

    def dataframe(self, sort_rows=False, sort_columns=False, cell_weights=True):
        """
        Returns a pandas dataframe for hypergraph indexed by the nodes and
        with column headers given by the edge names.

        Parameters
        ----------
        sort_rows : bool, optional, default=True
            sort rows based on hashable node names
        sort_columns : bool, optional, default=True
            sort columns based on hashable edge names
        cell_weights : bool, optional, default=True
            if self.isstatic then include cell weights

        """

        df = self.edges.dataframe.pivot(
            index=self.edges._data_cols[1],
            columns=self.edges._data_cols[0],
            values=self.edges._cell_weight_col,
        ).fillna(0)

        if sort_rows:
            df = df.sort_index("index")
        if sort_columns:
            df = df.sort_index("columns")
        if not cell_weights:
            df[df > 0] = 1

        return df

    @classmethod
    @warn_nwhy
    def from_bipartite(
        cls, B, set_names=("edges", "nodes"), name=None, static=False, use_nwhy=False
    ):
        """
        Static method creates a Hypergraph from a bipartite graph.

        Parameters
        ----------

        B: nx.Graph()
            A networkx bipartite graph. Each node in the graph has a property
            'bipartite' taking the value of 0 or 1 indicating a 2-coloring of
            the graph.

        set_names: iterable of length 2, optional, default = ['edges','nodes']
            Category names assigned to the graph nodes associated to each
            bipartite set

        name: hashable

        static: bool

        Returns
        -------
         : Hypergraph

        Notes
        -----
        A partition for the nodes in a bipartite graph generates a hypergraph.

            >>> import networkx as nx
            >>> B = nx.Graph()
            >>> B.add_nodes_from([1, 2, 3, 4], bipartite=0)
            >>> B.add_nodes_from(['a', 'b', 'c'], bipartite=1)
            >>> B.add_edges_from([(1, 'a'), (1, 'b'), (2, 'b'), (2, 'c'), /
                (3, 'c'), (4, 'a')])
            >>> H = Hypergraph.from_bipartite(B)
            >>> H.nodes, H.edges
            # output: (EntitySet(_:Nodes,[1, 2, 3, 4],{}), /
            # EntitySet(_:Edges,['b', 'c', 'a'],{}))

        """
        # TODO: Add filepath keyword to signatures here and with dataframe and
        #       numpy array
        edges = []
        nodes = []
        for n, d in B.nodes(data=True):
            if d["bipartite"] == 0:
                nodes.append(n)
            else:
                edges.append(n)

        if not bipartite.is_bipartite_node_set(B, nodes):
            raise HyperNetXError(
                "Error: Method requires a 2-coloring of a bipartite graph."
            )

        elist = []
        for e in list(B.edges):
            if e[0] in edges:
                elist.append([e[0], e[1]])
            else:
                elist.append([e[1], e[0]])
        df = pd.DataFrame(elist, columns=set_names)
        E = EntitySet(entity=df)
        name = name or "_"
        return Hypergraph(E, name=name, static=static)

    @classmethod
    @warn_nwhy
    def from_numpy_array(
        cls,
        M,
        node_names=None,
        edge_names=None,
        node_label="nodes",
        edge_label="edges",
        name=None,
        key=None,
        static=False,
        use_nwhy=False,
    ):
        """
        Create a hypergraph from a real valued matrix represented as a 2
        dimensionsl numpy array. The matrix is converted to a matrix of 0's
        and 1's so that any truthy cells are converted to 1's and all others
        to 0's.

        Parameters
        ----------
        M : real valued array-like object, 2 dimensions
            representing a real valued matrix with rows corresponding to nodes
            and columns to edges

        node_names : object, array-like, default=None
            List of node names must be the same length as M.shape[0].
            If None then the node names correspond to row indices with 'v'
            prepended.

        edge_names : object, array-like, default=None
            List of edge names must have the same length as M.shape[1].
            If None then the edge names correspond to column indices with 'e'
            prepended.

        name : hashable

        key : (optional) function
            boolean function to be evaluated on each cell of the array,
            must be applicable to numpy.array

        Returns
        -------
         : Hypergraph

        Note
        ----
        The constructor does not generate empty edges.
        All zero columns in M are removed and the names corresponding to these
        edges are discarded.


        """
        # Create names for nodes and edges
        # Validate the size of the node and edge arrays

        M = np.array(M)
        if len(M.shape) != (2):
            raise HyperNetXError("Input requires a 2 dimensional numpy array")
        # apply boolean key if available
        if key:
            M = key(M)

        if node_names is not None:
            nodenames = np.array(node_names)
            if len(nodenames) != M.shape[0]:
                raise HyperNetXError(
                    "Number of node names does not match number of rows."
                )
        else:
            nodenames = np.array([f"v{idx}" for idx in range(M.shape[0])])

        if edge_names is not None:
            edgenames = np.array(edge_names)
            if len(edgenames) != M.shape[1]:
                raise HyperNetXError(
                    "Number of edge_names does not match number of columns."
                )
        else:
            edgenames = np.array([f"e{jdx}" for jdx in range(M.shape[1])])

        data = np.stack(M.T.nonzero()).T
        labels = OrderedDict([(edge_label, edgenames), (node_label, nodenames)])
        E = EntitySet(data=data, labels=labels)
        return Hypergraph(E, name=name)

    @classmethod
    @warn_nwhy
    def from_dataframe(
        cls,
        df,
        columns=None,
        rows=None,
        name=None,
        fillna=0,
        transpose=False,
        transforms=[],
        key=None,
        node_label="nodes",
        edge_label="edges",
        static=False,
        use_nwhy=False,
    ):
        """
        Create a hypergraph from a Pandas Dataframe object using index to
        label vertices and Columns to label edges. The values of the dataframe
        are transformed into an incidence matrix. Note this is different than
        passing a dataframe directly into the Hypergraph constructor. The
        latter automatically generates a static hypergraph with edge and node
        labels given by the cell values.

        Parameters
        ----------
        df : Pandas.Dataframe
            a real valued dataframe with a single index

        columns : (optional) list, default = None
            restricts df to the columns with headers in this list.

        rows : (optional) list, default = None
            restricts df to the rows indexed by the elements in this list.

        name : (optional) string, default = None

        fillna : float, default = 0
            a real value to place in empty cell, all-zero columns will not
            generate an edge.

        transpose : (optional) bool, default = False
            option to transpose the dataframe, in this case df.Index will
            label the edges and df.columns will label the nodes, transpose is
            applied before transforms and key

        transforms : (optional) list, default = []
            optional list of transformations to apply to each column,
            of the dataframe using pd.DataFrame.apply().
            Transformations are applied in the order they are
            given (ex. abs). To apply transforms to rows or for additional
            functionality, consider transforming df using pandas.DataFrame
            methods prior to generating the hypergraph.

        key : (optional) function, default = None
            boolean function to be applied to dataframe. Must be defined on
            numpy arrays.

        See also
        --------
        from_numpy_array


        Returns
        -------
        : Hypergraph

        Notes
        -----
        The `from_dataframe` constructor does not generate empty edges.
        All-zero columns in df are removed and the names corresponding to these
        edges are discarded.
        Restrictions and data processing will occur in this order:

            1. column and row restrictions
            2. fillna replace NaNs in dataframe
            3. transpose the dataframe
            4. transforms in the order listed
            5. boolean key

        This method offers the above options for wrangling a dataframe into an
        incidence matrix for a hypergraph. For more flexibility we recommend
        you use the Pandas library to format the values of your dataframe
        before submitting it to this constructor.

        """

        if not isinstance(df, pd.DataFrame):
            raise HyperNetXError("Error: Input object must be a pandas dataframe.")

        if columns:
            df = df[columns]
        if rows:
            df = df.loc[rows]

        df = df.fillna(fillna)
        if transpose:
            df = df.transpose()

        # node_names = np.array(df.index)
        # edge_names = np.array(df.columns)

        for t in transforms:
            df = df.apply(t)
        if key:
            mat = key(df.values) * 1
        else:
            mat = df.values * 1

        params = {
            "node_names": np.array(df.index),
            "edge_names": np.array(df.columns),
            "name": name,
            "node_label": node_label,
            "edge_label": edge_label,
            "static": static,
        }
        return cls.from_numpy_array(mat, **params)

