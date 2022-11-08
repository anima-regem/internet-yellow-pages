import sys
import logging
import requests
import datetime
from iyp import IYP
import bz2
import json
# TODO move iyp to a better place
#from ...lib.wikihandy import Wikihandy

URL_BGPKIT_AS2REL = 'https://data.bgpkit.com/as2rel/as2rel-latest.json.bz2'

class Crawler(object):
    def __init__(self):

        # Reference information for data pushed to the wikibase
        self.reference = {
            'source': 'BGPKIT',
            'reference_url': URL_BGPKIT_AS2REL,
            'point_in_time': datetime.datetime.utcnow()
                .replace(hour=0, minute=0, second=0, microsecond=0)
            }

        # connection to IYP database
        self.iyp = IYP()


    def run(self):
        """Fetch the AS relationship file from BGPKIT website and process lines one by one"""

        req = requests.get(URL_BGPKIT_AS2REL, stream=True)
        if req.status_code != 200:
            sys.exit('Error while fetching AS relationships')

        for i, _ in enumerate(map(self.update_asn, json.load(bz2.open(req.raw)))):
            sys.stderr.write(f'\rProcessed {i} relationships')

        sys.stderr.write('\n')
        self.iyp.close()

    def update_asn(self, rel):
        as1_qid = self.iyp.get_node('AS', {'asn': rel['asn1']}, create=True)
        as2_qid = self.iyp.get_node('AS', {'asn': rel['asn2']}, create=True)

        statements = []
        statements.append( ['PEERS_WITH', as2_qid, self.reference] )  # Set relationship

        try:
            # Update AS name and country
            self.iyp.add_links(as1_qid, statements)

        except Exception as error:
            # print errors and continue running
            print('Error for: ', rel)
            print(error)

        return as1_qid, as2_qid

if __name__ == '__main__':

    scriptname = sys.argv[0].replace('/','_')[0:-3]
    FORMAT = '%(asctime)s %(processName)s %(message)s'
    logging.basicConfig(
            format=FORMAT, 
            filename='log/'+scriptname+'.log',
            level=logging.INFO, 
            datefmt='%Y-%m-%d %H:%M:%S'
            )
    logging.info("Started: %s" % sys.argv)

    asnames = Crawler()
    asnames.run()
