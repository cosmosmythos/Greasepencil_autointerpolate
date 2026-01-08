#include "stdafx.h"
#include "ContractLoops.h"
#include "IsLoopContractible.h"
std::vector<edge_descriptor> contractLoops(G & g, const cv::Mat & origMask, const std::vector<MyPolyline>& polys)
{
	using namespace boost;
	int n = boost::num_vertices(g);
	std::vector<edge_descriptor> result; //removed edges

	std::vector<std::vector<cv::Point2f>> realIncontractibleLoops;

	PV_VLOG("Reeb graph: " << num_vertices(g) << " vertices, " << num_edges(g) << " edges.");

	int c = 0;
	//do
	//{
		std::map<size_t, std::vector < graph_traits < G >::vertex_descriptor >> p;

		PV_VLOG_NL("Computing min spaning trees...");
		size_t treeRoot = 0;
		//create a boolean map if an edge is in the sp tree

		std::map<graph_traits<G>::edge_descriptor, bool> isInSpTree;
		std::vector<bool> vertexCovered(num_vertices(g));
		while (treeRoot < num_vertices(g))
		{
			p[treeRoot] = std::vector< graph_traits < G >::vertex_descriptor>(num_vertices(g));
			prim_minimum_spanning_tree(g, &p[treeRoot][0], boost::root_vertex(treeRoot).weight_map(boost::get(&Edge::weight, g)));

			vertexCovered[treeRoot] = true;

			for (size_t i = 0; i < num_vertices(g); ++i)
			{
				auto ee = edge(i, p[treeRoot][i], g);
				if (ee.second)
				{
					isInSpTree[ee.first] = true;
					vertexCovered[i] = true;
					vertexCovered[p[treeRoot][i]] = true;
				}
			}

			for (; treeRoot < num_vertices(g); ++treeRoot)
				if (!vertexCovered[treeRoot])
					break;
		}
		PV_VLOG("done.");

		//now for every edge not in the tree, find the smallest loop containing it
		auto eii = edges(g);

		for (auto it = eii.first; it != eii.second; ++it)
		{
			if (!isInSpTree[*it])
				g[*it].weight = 1e10;
		}


		std::vector < std::vector<edge_descriptor>> loops, incontractibleLoops /*for debug only*/;
		std::vector<std::vector<cv::Point2f>> realLoops;
		std::vector<edge_descriptor> origEdge, origEdgeForIncontractibleLoops;


		PV_VLOG_NL("Computing loops...");
		c = 0;
		int tmpLoopIdx = 0;
		for (auto it = eii.first; it != eii.second; ++it)
		{
			if (!isInSpTree[*it])
			{
				std::vector<vertex_descriptor> pDij(num_vertices(g));
				std::vector<double> dDij(num_vertices(g));
				auto predMap = make_iterator_property_map(pDij.begin(), get(&Cluster::clusterIdx, g));
				auto distMap = make_iterator_property_map(dDij.begin(), get(&Cluster::clusterIdx, g));
				size_t source = it->m_source;
				dijkstra_shortest_paths(g, it->m_source,
					predecessor_map(predMap).
					distance_map(distMap).weight_map(get(&Edge::weight,g)));

				//now record the path
				std::vector<edge_descriptor> loop;
				auto cur = it->m_target;
				while (cur != it->m_source)
				{
					edge_descriptor ed = edge(cur, pDij[cur], g).first;
					loop.push_back(ed);
					cur = pDij[cur];
				}
				loop.push_back(*it);
				realLoops.push_back({});
				
				/*if (loop.size() > 100)
				{
					PV_LOG_NL("BIG LOOP: (size = " << loop.size() << "), ");
					PV_LOG("non-tree edge: " << it->m_source << "-" << it->m_target);
					PV_LOG_NL("loop: ");
					for (auto tt : loop)
					{
						PV_LOG_NL(tt.m_source << " ");
					}
				}*/

				if (isLoopContractible(loop, origMask, g, polys,realLoops.back()))
				{
					loops.push_back(loop);
					c += loop.size();
					origEdge.push_back(*it);
				}
				else
				{
					// std::cout << "Incontractible loop: ";
					// for (const auto& e : loop)
					// {
					// 	std::cout << e.m_source << " ";
					// }
					// std::cout << std::endl;
					incontractibleLoops.push_back(loop);
					origEdgeForIncontractibleLoops.push_back(*it);
					realIncontractibleLoops.push_back(realLoops.back());
				}
				++tmpLoopIdx;
			}
		}
		PV_VLOG("done, found " << c << " edges to remove");

		PV_VLOG_NL("Contracting loops...");
		/*for (int i = 0; i < loops.size(); ++i)
		{
			PV_LOG("Loop " << i);
			for (const auto& e : loops[i])
			{
				PV_LOG_NL(e.m_source << " ");
			}
			PV_LOG(loops[i].back().m_target);
		}*/
		auto removedEdges = contract_edges(loops, g);
		if (!removedEdges.empty())
			result.insert(result.end(), removedEdges.begin(), removedEdges.end());
		PV_VLOG("done.");
	//} while (c != 0);
	

	PV_VLOG("all done.");
	return result;
}
