#include <expat.h>

int main(void)
{
    XML_Parser parser = XML_ParserCreate(NULL);
    if (parser == NULL)
        return 1;
    XML_ParserFree(parser);
    return 0;
}
