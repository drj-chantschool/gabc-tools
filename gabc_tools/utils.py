def strcmp(s1,s2):
    idxs = [idx for idx,(x,y) in enumerate(zip(s1,s2)) if x != y]
    if idxs:
        print(f'Error at character {idxs[0]}:')
        print(s1[ max(0,idxs[0]-20):idxs[0]+20])
        print(s2[ max(0,idxs[0]-20):idxs[0]+20])
        print( ''.join( '^' if idx in idxs else ' ' for idx in range(idxs[0] - 20, idxs[0] + 20) if idx >= 0) )
    elif len(s1) != len(s2):
        print('unequal length:')
        print( s1[len(s2):], s2[len(s1):] )
