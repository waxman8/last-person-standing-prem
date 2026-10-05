/**
 * Shared utility functions for Last Person Standing frontend
 */

window.LMS_UTILS = {
    /**
     * Translates internal stage names and numbers to friendly labels.
     */
    STAGE_MAP: {
        1: 'Group Stage 1',
        2: 'Group Stage 2',
        3: 'Group Stage 3',
        4: 'Round of 32',
        5: 'Round of 16',
        6: 'Quarter Finals',
        7: 'Semi Finals',
        8: 'Final'
    },

    /**
     * Translates API stage names and gameweek numbers into friendly display names.
     * @param {Object} gw - The gameweek object (must have .number)
     * @param {Array} fixtures - (Optional) List of fixtures for this gameweek
     * @returns {string} Friendly stage name
     */
    getFriendlyStageName(gw, fixtures) {
        if (!gw) return 'Loading...';
        
        // Fallback to fixture-based detection first to see if it's a regular league match
        if (fixtures && fixtures.length > 0) {
            const stage = fixtures[0].stage;
            if (stage === 'REGULAR' || stage === 'REGULAR_SEASON' || stage === 'COMPETITION_MATCHDAY') {
                return `Game Week ${gw.number}`;
            }

            const mapping = {
                'GROUP_STAGE': `Group Stage ${gw.number}`,
                'ROUND_OF_32': 'Round of 32',
                'ROUND_OF_16': 'Round of 16',
                'QUARTER_FINALS': 'Quarter Finals',
                'SEMI_FINALS': 'Semi Finals',
                'FINAL': 'Final'
            };
            
            if (mapping[stage]) {
                return mapping[stage];
            }
        }

        // For Prem 26/27 (and other leagues), we prefer "Game Week"
        // If we don't have fixtures, we'll still use the number but avoid the tournament map if possible
        // but since we don't know the competition type here easily, we'll just return Game Week by default
        // unless it's a known tournament number and we want to keep that logic for now.
        
        return `Game Week ${gw.number}`;
    }
};
