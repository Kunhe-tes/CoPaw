
import { AgentScopeRuntimeContentType, IAgentScopeRuntimeRequest, ITextContent } from '../types';
import { useMemo } from 'react';
import { Bubble } from '@/chat';
import MessageActions from './MessageActions';

export default function AgentScopeRuntimeRequestCard(props: {
  data: IAgentScopeRuntimeRequest;
  messageId?: string;
  createdAt?: number;
}) {
  const textContent = useMemo(() => {
    return props.data.input[0].content.find(c => c.type === AgentScopeRuntimeContentType.TEXT);
  }, [props.data.input]);

  const cards = useMemo(() => {

    return props.data.input[0].content.reduce<any>((p, c) => {
      if (c.type === AgentScopeRuntimeContentType.TEXT) {
        p.push({
          code: 'Text',
          data: {
            content: c.text,
            raw: true,
          },
        });
      }

      if (c.type === AgentScopeRuntimeContentType.IMAGE) {
        const imageCard = p.find((item: any) => item.code === 'Image');
        if (!imageCard) {
          p.push({
            code: 'Images',
            data: [{ url: c.image_url }],
          });

        } else {
          imageCard.data.push({ url: c.image_url });
        }
      }

      if (c.type === AgentScopeRuntimeContentType.FILE) {
        const fileCard = p.find((item: any) => item.code === 'Files');
        if (!fileCard) {
          p.push({
            code: 'Files',
            data: [{ url: c.file_url, name: c.file_name, size: c.file_size }],
          });
        } else {
          fileCard.data.push({ url: c.file_url, name: c.file_name, size: c.file_size });
        }
      }
      return p;
    }, []);
  }, [props.data.input]);

  if (!cards?.length) return null;

  const text = (textContent as ITextContent | undefined)?.text || '';

  return (
    <div className="request-card-container">
      <Bubble role="user" cards={cards} createdAt={props.createdAt}></Bubble>
      {props.createdAt && (
        <MessageActions
          content={text}
          timestamp={props.createdAt}
        />
      )}
      <style>{`
        .request-card-container {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
        }
      `}</style>
    </div>
  );
}

