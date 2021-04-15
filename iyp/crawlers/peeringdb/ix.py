import sys
import logging
from iyp.wiki.wikihandy import Wikihandy
import requests
import json

# URL to peeringdb API for exchange points
URL_PDB_IXS = 'https://peeringdb.com/api/ix'

# API endpoint for LAN prefixes
URL_PDB_LAN = 'https://peeringdb.com/api/ixlan'

# Label used for the class/item representing the exchange point IDs
IXID_LABEL = 'PeeringDB IX ID' 
# Label used for the class/item representing the organization IDs
ORGID_LABEL = 'PeeringDB organization ID' 

class Crawler(object):
    def __init__(self):
        """Create an item representing the PeeringDB exchange point ID class if 
        doesn't already exist. And fetch QIDs for exchange points already in the
        wikibase."""
    
        # Helper for wiki access
        self.wh = Wikihandy()

        # Get the QID of the item representing PeeringDB IX IDs
        ixid_qid = self.wh.get_qid(IXID_LABEL,
                create={                                                            # Create it if it doesn't exist
                    'summary': 'add PeeringDB ix IDs',                             # Commit message
                    'description': 'Identifier for an exchange point in the PeeringDB database' # Description
                    })

        # Load the QIDs for ix already available in the wikibase
        self.ixid2qid = self.wh.extid2qid(qid=ixid_qid)
        # Load the QIDs for peeringDB organizations
        self.orgid2qid = self.wh.extid2qid(label=ORGID_LABEL)

        # Added properties will have this reference information
        self.today = self.wh.today()
        self.reference = [
                (self.wh.get_pid('source'), self.wh.get_qid('PeeringDB')),
                (self.wh.get_pid('reference URL'), URL_PDB_IXS),
                (self.wh.get_pid('point in time'), self.today)
                ]

    def run(self):
        """Fetch ixs information from PeeringDB and push to wikibase. 
        Using multiple threads for better performances."""

        req = requests.get(URL_PDB_IXS)
        if req.status_code != 200:
            sys.exit('Error while fetching IXs data')
        ixs = json.loads(req.text)['data']

        self.wh.login() # Login once for all threads

        for i, ix in enumerate(ixs):

            # Get more info for this IX
            req = requests.get(f'{URL_PDB_IXS}/{ix["id"]}')
            if req.status_code != 200:
                sys.exit('Error while fetching IXs data')
            ix_info = json.loads(req.text)['data'][0]

            # Update info in wiki
            self.update_ix(ix_info)

            sys.stderr.write(f'\rProcessing... {i+1}/{len(ixs)}')


    def update_ix(self, ix):
        """Add the ix to wikibase if it's not already there and update its
        properties."""

        # set property name
        statements = [ 
                [self.wh.get_pid('instance of'), self.wh.get_qid('Internet exchange point')],
                [self.wh.get_pid('name'), ix['name'].strip(), self.reference] ] 

        # link to corresponding organization
        org_qid = self.orgid2qid.get(str(ix['org_id']))
        if org_qid is not None:
            statements.append( [self.wh.get_pid('managed by'), org_qid, self.reference])
        else:
            print('Error this organization is not in wikibase: ',ix['org_id'])

        # set property country
        if ix['country']:
            country_qid = self.wh.country2qid(ix['country'])
            if country_qid is not None:
                statements.append([self.wh.get_pid('country'), country_qid, self.reference])

        # set property website
        if ix['website']:
            statements.append([ self.wh.get_pid('website'), ix['website'], self.reference])

        # set traffic webpage 
        if ix['url_stats']:
            statements.append([ 
                self.wh.get_pid('website'), ix['url_stats'],  # statement
                self.reference,                               # reference 
                [ (self.wh.get_pid('instance of'), self.wh.get_qid('traffic statistics')), ] # qualifier
                ])

        ix_qid = self.ix_qid(ix) 
        # Update name, website, and organization for this IX
        self.wh.upsert_statements('update peeringDB ixs', ix_qid, statements )

        # update LAN corresponding to this IX
        if 'ixlan_set' in ix:
            for ixlan in ix['ixlan_set']:
                pfx_url = f'{URL_PDB_LAN}/{ixlan["id"]}'
                pfx_ref = [
                        (self.wh.get_pid('source'), self.wh.get_qid('PeeringDB')),
                        (self.wh.get_pid('reference URL'), pfx_url),
                        (self.wh.get_pid('point in time'), self.today)
                        ]

                req = requests.get(pfx_url)
                if req.status_code != 200:
                    sys.exit('Error while fetching IXs data')
                lans = json.loads(req.text)['data']

                for lan in lans:
                    for prefix in lan['ixpfx_set']:
                        pfx_qid = self.wh.prefix2qid(prefix['prefix'], create=True)

                        pfx_stmts = [ 
                                [self.wh.get_pid('instance of'), self.wh.get_qid('peering LAN'), pfx_ref],
                                [self.wh.get_pid('managed by'), ix_qid, pfx_ref]
                                ]

                        self.wh.upsert_statements('update peeringDB ixlan', pfx_qid, pfx_stmts )

        return ix_qid


    def ix_qid(self, ix):
        """Find the ix QID for the given ix.
        If this ix is not yet registered in the wikibase then add it.

        Return the ix QID."""

        # Check if the IX is in the wikibase
        if str(ix['id']) not in self.ixid2qid :
            # Set properties for this new ix
            ix_qualifiers = [
                    (self.wh.get_pid('instance of'), self.wh.get_qid(IXID_LABEL)),
                    ]
            statements = [ 
                    (self.wh.get_pid('instance of'), self.wh.get_qid('Internet exchange point')),
                    (self.wh.get_pid('external ID'), str(ix['id']), [],  ix_qualifiers) ]

            # Add this ix to the wikibase
            ix_qid = self.wh.add_item('add new peeringDB IX', 
                    label=ix['name'], description=ix['name_long'], 
                    statements=statements)
            # keep track of this QID
            self.ixid2qid[str(ix['id'])] = ix_qid

        return self.ixid2qid[str(ix['id'])]


# Main program
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

    pdbn = Crawler()
    pdbn.run()

